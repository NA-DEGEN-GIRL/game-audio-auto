const $ = (s) => document.querySelector(s);
const briefs = {
  bgm: ["BACKGROUND MUSIC", "햇살 좋은 공원의 배경음악", "피치카토 현악기와 목관, 마림바가 어우러지는 밝고 아기자기한 연주곡."],
  crowd: ["PARK AMBIENCE", "사람들로 채워지는 공원", "야외에서 겹쳐 들리는 대화, 웃음, 발걸음. 또렷한 대사 없이 자연스럽게."],
  drop: ["ROLLER COASTER", "떨어지는 순간, 꺄아악!", "짧은 숨 들이마심부터 들뜬 비명과 환호, 안도하는 웃음까지. 목소리 중심의 효과음."],
  boss: ["BOSS ROOM · GREGORIYA", "광란의 그레고리야", "60초 보스 전투곡. A·B는 최초 프롬프트, C는 공포 방향으로 수정한 프롬프트입니다. D는 ElevenLabs v2.5에 최초 프롬프트를 그대로 넣은 버전 비교용 곡입니다. 무한 루프는 미편집."]
};
let catalog, category = "bgm", take = "A", signature = "", queue = [], sequenceActive = false;
const requestedTake = new URLSearchParams(location.search).get("take");
if (/^[A-Z]$/.test(requestedTake || "")) take = requestedTake;
const requestedCategory = new URLSearchParams(location.search).get("category");
if (Object.hasOwn(briefs, requestedCategory)) category = requestedCategory;
function status(text) { $("#play-status").textContent = text; }
function stopAll() { document.querySelectorAll("audio").forEach(a => a.pause()); queue = []; sequenceActive = false; }
function source(track) { return $("#matched").checked && track.matched ? track.matched : track.original; }
function setupAudio(audio) {
  audio.volume = Number($("#volume").value);
  audio.loop = $("#loop").checked && !sequenceActive;
  audio.addEventListener("play", () => {
    document.querySelectorAll("audio").forEach(other => { if (other !== audio) other.pause(); });
    document.querySelectorAll(".card").forEach(c => c.classList.toggle("playing", c.contains(audio)));
    status(`${audio.getAttribute("aria-label")} 재생 중`);
  });
  audio.addEventListener("pause", () => {
    audio.closest(".card")?.classList.remove("playing");
    if (!audio.ended && ![...document.querySelectorAll("audio")].some(a => !a.paused)) status("일시정지했습니다.");
  });
  audio.addEventListener("ended", () => {
    audio.closest(".card")?.classList.remove("playing");
    if (sequenceActive && queue.length) playQueued();
    else {
      sequenceActive = false;
      document.querySelectorAll("audio").forEach(a => a.loop = $("#loop").checked);
      status("재생을 마쳤습니다. 다른 후보도 들어보세요.");
    }
  });
  audio.addEventListener("error", () => { queue = []; sequenceActive = false; status("음원을 재생하지 못했습니다. 페이지를 새로고침해 주세요."); });
}
function playQueued() {
  const next = queue.shift();
  next.loop = false;
  next.currentTime = 0;
  next.play().catch(() => { sequenceActive = false; queue = []; status("해당 카드의 재생 버튼을 눌러 주세요."); });
}
function render() {
  if (!catalog) return;
  const candidates = [...new Set(catalog.tracks.filter(t => t.category === category).map(t => t.candidate))].sort();
  if (candidates.length && !candidates.includes(take)) take = candidates[0];
  document.querySelectorAll("[data-category]").forEach(b => b.setAttribute("aria-pressed", b.dataset.category === category));
  document.querySelectorAll("[data-take]").forEach(b => {
    b.hidden = candidates.length > 0 && !candidates.includes(b.dataset.take);
    b.setAttribute("aria-pressed", b.dataset.take === take);
  });
  $(".scene").hidden = category === "boss";
  const [tag, title, brief] = briefs[category];
  $("#category-tag").textContent = tag;
  $("#category-title").textContent = title;
  $("#brief").textContent = brief;
  $("#cards").replaceChildren();
  const providers = catalog.providers.filter(p => p.categories.includes(category));
  for (const provider of providers) {
    const track = catalog.tracks.find(t => t.category === category && t.provider === provider.id && t.candidate === take);
    const card = document.createElement("article");
    card.className = `card${track ? "" : " pending"}`;
    // Catalog content is inserted as text, never as markup.
    card.innerHTML = '<div class="card-top"><span class="provider-symbol"></span><span class="chip"></span></div><h3></h3><div class="model"></div>';
    card.querySelector(".provider-symbol").textContent = provider.local ? "∿" : "Ⅱ";
    const chip = card.querySelector(".chip");
    chip.textContent = provider.local ? "LOCAL MODEL" : "ELEVENLABS";
    chip.classList.toggle("cloud", !provider.local);
    card.querySelector("h3").textContent = provider.name;
    card.querySelector(".model").textContent = track?.model || provider.models?.[category] || provider.model;
    if (track) {
      const line = document.createElement("div"); line.className = "track-line";
      const name = document.createElement("span"); name.className = "take-name"; name.textContent = `후보 ${take}`;
      const detail = document.createElement("span"); detail.textContent = `${track.duration.toFixed(1)}초 · ${$("#matched").checked && track.matched ? "비교 음량" : "원본"}`;
      line.append(name, detail); card.append(line);
      const audio = document.createElement("audio"); audio.controls = true; audio.preload = "metadata"; audio.src = source(track); audio.dataset.track = track.id;
      audio.setAttribute("aria-label", `${provider.name} ${title} 후보 ${take}`); setupAudio(audio);
      const play = document.createElement("button"); play.className = "play-button"; play.textContent = "▶ 재생"; play.setAttribute("aria-label", `${provider.name} 후보 ${take} 재생`);
      play.addEventListener("click", () => { queue = []; sequenceActive = false; audio.loop = $("#loop").checked; if (audio.paused) audio.play().catch(() => status("재생하지 못했습니다. 음원 컨트롤에서 다시 시도해 주세요.")); else audio.pause(); });
      audio.addEventListener("play", () => { play.textContent = "Ⅱ 일시정지"; play.setAttribute("aria-label", `${provider.name} 후보 ${take} 일시정지`); });
      audio.addEventListener("pause", () => { play.textContent = "▶ 재생"; play.setAttribute("aria-label", `${provider.name} 후보 ${take} 재생`); });
      card.append(play, audio);
      const link = document.createElement("a"); link.className = "download"; link.href = track.original; link.download = `${track.id}.wav`; link.textContent = "원본 WAV 저장 ↗"; card.append(link);
    } else {
      const note = document.createElement("p"); note.className = "pending-note"; note.textContent = provider.status?.[`${category}:${take}`] || provider.status?.[category] || "로컬 음원을 준비하고 있습니다. 완성되면 여기에 자동으로 추가됩니다."; card.append(note);
    }
    $("#cards").append(card);
  }
  $("#sequence").disabled = $("#cards").querySelectorAll("audio").length < 2;
}
document.querySelectorAll("[data-category]").forEach(b => b.addEventListener("click", () => {
  stopAll(); category = b.dataset.category;
  document.querySelectorAll("[data-category]").forEach(other => other.setAttribute("aria-pressed", other === b));
  render(); status("재생 버튼을 누르면 바로 들을 수 있어요.");
}));
document.querySelectorAll("[data-take]").forEach(b => b.addEventListener("click", () => {
  stopAll(); take = b.dataset.take;
  document.querySelectorAll("[data-take]").forEach(other => other.setAttribute("aria-pressed", other === b));
  render(); status(`후보 ${take}를 선택했습니다.`);
}));
$("#matched").addEventListener("change", () => { stopAll(); render(); });
$("#loop").addEventListener("change", () => { queue = []; sequenceActive = false; document.querySelectorAll("audio").forEach(a => a.loop = $("#loop").checked); });
$("#volume").addEventListener("input", () => document.querySelectorAll("audio").forEach(a => a.volume = Number($("#volume").value)));
$("#sequence").addEventListener("click", () => { stopAll(); queue = [...$("#cards").querySelectorAll("audio")]; if (queue.length) { sequenceActive = true; playQueued(); } });
setupAudio($("#scene-audio"));
async function refresh() {
  try {
    const response = await fetch("/api/catalog", {cache: "no-store"});
    if (!response.ok) throw Error();
    const data = await response.json();
    const next = JSON.stringify(data);
    $("#connection").textContent = `${data.tracks.filter(t => t.category !== "mix").length}개 음원 · 이 PC에서 재생`;
    if (signature !== next && ![...document.querySelectorAll("audio")].some(a => !a.paused)) {
      catalog = data; signature = next; render();
      const mix = catalog.tracks.find(t => t.category === "mix");
      if (mix && $("#scene-audio").getAttribute("src") !== mix.original) $("#scene-audio").src = mix.original;
    }
  } catch { $("#connection").textContent = "서버 연결을 확인해 주세요"; }
}
refresh(); setInterval(refresh, 5000);
