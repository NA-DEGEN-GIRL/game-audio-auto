const $ = (s) => document.querySelector(s);
const briefs = {
  bgm: ["BACKGROUND MUSIC", "햇살 좋은 공원의 배경음악", "피치카토 현악기와 목관, 마림바가 어우러지는 밝고 아기자기한 연주곡."],
  crowd: ["PARK AMBIENCE", "사람들로 채워지는 공원", "야외에서 겹쳐 들리는 대화, 웃음, 발걸음. 또렷한 대사 없이 자연스럽게."],
  drop: ["ROLLER COASTER", "떨어지는 순간, 꺄아악!", "짧은 숨 들이마심부터 들뜬 비명과 환호, 안도하는 웃음까지. 목소리 중심의 효과음."],
  boss: ["BOSS ROOM · GREGORIYA", "광란의 그레고리야", "60초 보스 전투곡. A·B는 최초 프롬프트, C는 공포 방향으로 수정한 프롬프트입니다. D는 ElevenLabs v2.5에 최초 프롬프트를 그대로 넣은 버전 비교용 곡입니다. 무한 루프는 미편집."],
  legendary: ["LEGENDARY LOOT", "전설 아이템이 떨어지는 순간", "새 후보 X·Y는 Q, Z·AA는 P, AB·AC는 O의 +6반음·+7반음 버전입니다. 청동종 F 기준이며 길이는 모두 4.05초입니다. 아래에서 +4·+5반음 버전과 Q·P·O 원본도 비교할 수 있습니다."],
  dialogue: ["CHARACTER VOICE · GREGORIYA", "광란의 그레고리야의 목소리", "평상시·위협·분노는 같은 대사를, 마지막은 광기 어린 웃음을 비교합니다. Gemini의 설계한 목소리와 ElevenLabs의 선택한 목소리는 서로 다릅니다. 각 목소리의 일관성, 한국어 발음과 장면별 연기를 들어보세요."],
  "voice-models": ["ELEVENLABS · V3 / V4", "같은 목소리, 새로 나온 v4", "Callum의 동일한 대사·감정 태그·시드로 비교합니다. v3는 기존 음원, v4는 새로 생성한 음원입니다. 같은 시드여도 같은 연기를 보장하지 않습니다. EQ·밀도 보정 없이 비교하며, 음량 맞추기는 일정한 게인만 적용합니다."],
  "boss-voice": ["BOSS VOICE · KOREAN / ENGLISH", "보스 연기, 한국어와 영어", "E형은 낮고 위협적인 발성, F형은 구체적으로 지시한 억눌린 분노입니다. 같은 대사를 한국어·영어로 비교합니다. ElevenLabs는 Callum, Gemini는 기존 설계 목소리로 서로 다릅니다. Gemini에는 기본 밀도 보정이 적용됩니다. G는 한국어 연기 지시, H는 위험한 광기, R3·R4는 기존 음원입니다. 언어·지시 필터로 좁혀 들어보세요."],
  "boss-space": ["BOSS ROOM · REVERB STUDY", "목소리 뒤로 퍼지는 보스룸의 울림", "E형 연기의 현재 상태·짧은 공간·넓은 석조 보스룸을 비교합니다. 한국어와 영어, ElevenLabs와 Gemini 각각 같은 음원에 잔향만 추가했습니다. Gemini의 기존 밀도 보정은 유지했습니다. 피치 변경과 새 음성 생성은 없습니다. 비교 음량을 맞춘 스테레오 미리듣기이며 게임 엔진의 공간 음향은 별도로 적용해야 합니다."],
  "boss-v3-gemini": ["BOSS AUDITION · ELEVEN V3 / GEMINI", "세 가지 보스 연기, 두 가지 언어", "낮은 위협·폭발하는 분노·위험한 광기를 한국어와 영어로 새로 생성했습니다. V1~V6는 Eleven v3의 Callum, G1~G6는 Gemini의 기존 설계 목소리입니다. 같은 번호끼리 같은 언어·톤입니다. Gemini는 기본 밀도 강화, Eleven v3는 추가 보정 없이 비교하며 잔향은 넣지 않았습니다. F의 긴 연기 지시는 사용하지 않았습니다."]
};
const bossCategories = ["boss-voice", "boss-space", "boss-v3-gemini"];
let catalog, category = "bgm", take = "A", signature = "", queue = [], sequenceActive = false;
const processingVersions = ["clean", "clean-eq", "clean-studio", "clear-presence", "clear-lowcut", "clear-air", "clear-density", "clear-detail"];
const processingNames = {clean: "새 음색 원본", "clean-eq": "EQ 보정", "clean-studio": "EQ + 음량 정리", "clear-presence": "발음 강조", "clear-lowcut": "저음 억제", "clear-air": "밝은 고역", "clear-density": "밀도 강화", "clear-detail": "작은 발음 살리기"};
const processingBrief = "같은 원본 연기에 서로 다른 보정을 적용한 실험입니다. 음색과 감정의 강약이 어떻게 달라지는지 비교해 보세요.";
let dialogueVersion = new URLSearchParams(location.search).get("dialogue_version");
if (!["original", "neutral-retry", ...processingVersions].includes(dialogueVersion)) dialogueVersion = null;
let dialogueProcessing = new URLSearchParams(location.search).get("dialogue_view") === "processing";
let dialogueLine = new URLSearchParams(location.search).get("line");
if (!/^[A-D]$/.test(dialogueLine || "")) dialogueLine = "A";
const requestedTake = new URLSearchParams(location.search).get("take");
if (/^[A-Z]$/.test(requestedTake || "")) take = requestedTake;
const requestedCategory = new URLSearchParams(location.search).get("category");
if (Object.hasOwn(briefs, requestedCategory)) category = requestedCategory;
let bossLanguage = "all", bossDirection = "all", bossProvider = "all";
function status(text) { $("#play-status").textContent = text; }
function stopAll() { document.querySelectorAll("audio").forEach(a => a.pause()); queue = []; sequenceActive = false; }
function source(track) { return $("#matched").checked && track.matched ? track.matched : track.original; }
function selectedDialogueVersion() {
  const versions = new Set(catalog.tracks.filter(t => t.category === "dialogue" && t.provider === "gemini" && !t.superseded).map(t => t.dialogue_version || "original"));
  return versions.has(dialogueVersion) ? dialogueVersion : versions.has("clean") ? "clean" : "original";
}
function visibleDialogueTrack(track) {
  if (track.category !== "dialogue" || track.superseded) return false;
  if (dialogueProcessing) return track.candidate === dialogueLine && (track.provider === "elevenlabs" || (track.provider === "gemini" && processingVersions.includes(track.dialogue_version)));
  if (track.provider !== "gemini") return true;
  const selected = selectedDialogueVersion();
  const version = track.dialogue_version || "original";
  if (selected === "neutral-retry" && version === "original") {
    return !catalog.tracks.some(t => t.category === "dialogue" && t.provider === "gemini" && !t.superseded && t.candidate === track.candidate && t.dialogue_version === "neutral-retry");
  }
  return version === selected;
}
function dialogueProcessingOrder(track) {
  return track.provider === "gemini" ? processingVersions.indexOf(track.dialogue_version) : processingVersions.length;
}
function visibleBossVoiceTrack(track, target = "boss-voice") {
  return track.category === target && !track.superseded
    && (bossLanguage === "all" || track.language === bossLanguage)
    && (bossProvider === "all" || track.provider === bossProvider)
    && (target !== "boss-voice" || bossDirection === "all" || track.direction === bossDirection);
}
function saveDialogueSelection() {
  const url = new URL(location.href);
  url.searchParams.set("category", "dialogue");
  url.searchParams.set("dialogue_version", selectedDialogueVersion());
  if (dialogueProcessing) {
    url.searchParams.set("dialogue_view", "processing");
    url.searchParams.set("line", dialogueLine);
  } else {
    url.searchParams.delete("dialogue_view");
    url.searchParams.delete("line");
  }
  history.replaceState(null, "", url);
}
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
  $("#cards").classList.toggle("dialogue-pairs", (category === "dialogue" && !dialogueProcessing) || ["voice-models", "boss-voice", "boss-v3-gemini"].includes(category));
  $("#cards").classList.toggle("dialogue-processing-grid", (category === "dialogue" && dialogueProcessing) || category === "boss-space");
  const compareVariants = ["legendary", "dialogue", "voice-models", ...bossCategories].includes(category);
  $(".takes").hidden = compareVariants;
  $("#dialogue-processing-control").hidden = category !== "dialogue";
  $("#dialogue-processing").checked = dialogueProcessing;
  $("#dialogue-line-control").hidden = category !== "dialogue" || !dialogueProcessing;
  $("#dialogue-line").value = dialogueLine;
  $("#dialogue-version-control").hidden = category !== "dialogue" || dialogueProcessing;
  $("#boss-language-control").hidden = !bossCategories.includes(category);
  $("#boss-provider-control").hidden = !bossCategories.includes(category);
  $("#boss-direction-control").hidden = category !== "boss-voice";
  $("#dialogue-version").value = selectedDialogueVersion();
  for (const option of $("#dialogue-version").options) {
    option.disabled = !catalog.tracks.some(t => t.category === "dialogue" && t.provider === "gemini" && !t.superseded && (t.dialogue_version || "original") === option.value);
  }
  $('[data-category="legendary"] small').textContent = `${catalog.tracks.filter(t => t.category === "legendary" && !t.superseded).length}개`;
  $('[data-category="dialogue"] small').textContent = `${catalog.tracks.filter(visibleDialogueTrack).length}개`;
  $('[data-category="voice-models"] small').textContent = `${catalog.tracks.filter(t => t.category === "voice-models").length}개`;
  $('[data-category="boss-voice"] small').textContent = `${catalog.tracks.filter(t => visibleBossVoiceTrack(t)).length}개`;
  $('[data-category="boss-space"] small').textContent = `${catalog.tracks.filter(t => visibleBossVoiceTrack(t, "boss-space")).length}개`;
  $('[data-category="boss-v3-gemini"] small').textContent = `${catalog.tracks.filter(t => visibleBossVoiceTrack(t, "boss-v3-gemini")).length}개`;
  const candidates = [...new Set(catalog.tracks.filter(t => t.category === category).map(t => t.candidate))].sort();
  if (candidates.length && !candidates.includes(take)) take = candidates[0];
  document.querySelectorAll("[data-category]").forEach(b => b.setAttribute("aria-pressed", b.dataset.category === category));
  document.querySelectorAll("[data-take]").forEach(b => {
    b.hidden = candidates.length > 0 && !candidates.includes(b.dataset.take);
    b.setAttribute("aria-pressed", b.dataset.take === take);
  });
  $(".scene").hidden = !["bgm", "crowd", "drop"].includes(category);
  const [tag, title, brief] = briefs[category];
  $("#category-tag").textContent = tag;
  $("#category-title").textContent = title;
  const versionBrief = {
    "neutral-retry": " 이 대조군은 기존 목소리에서 A의 연기 지시만 제거해 다시 생성했습니다. B·C·D는 기존 음원입니다.",
    "clean-eq": " 선명도 재설계 음원의 후처리 비교본입니다. 같은 연기이며 새로 생성하지 않았습니다.",
    "clean-studio": " 선명도 재설계 음원의 후처리 비교본입니다. 같은 연기이며 새로 생성하지 않았습니다."
  };
  const currentVersion = selectedDialogueVersion();
  const extraBrief = currentVersion.startsWith("clear-") ? ` ${processingBrief}` : versionBrief[currentVersion] || "";
  $("#brief").textContent = category === "dialogue" && dialogueProcessing
    ? `Gemini의 ${processingBrief} ElevenLabs는 별도 목소리로 생성한 비교 음원입니다.`
    : brief + (category === "dialogue" ? extraBrief : "");
  $("#cards").replaceChildren();
  const providers = catalog.providers.filter(p => p.categories.includes(category));
  const entries = compareVariants
    ? catalog.tracks.filter(t => category === "dialogue" ? visibleDialogueTrack(t) : bossCategories.includes(category) ? visibleBossVoiceTrack(t, category) : t.category === category && !t.superseded)
        .sort((a, b) => category === "dialogue" && dialogueProcessing ? dialogueProcessingOrder(a) - dialogueProcessingOrder(b) : (a.display_order ?? 100) - (b.display_order ?? 100) || a.candidate.localeCompare(b.candidate))
        .map(track => ({track, provider: providers.find(p => p.id === track.provider)}))
        .filter(entry => entry.provider)
    : providers.map(provider => ({provider, track: catalog.tracks.find(t => t.category === category && t.provider === provider.id && t.candidate === take)}));
  for (const {provider, track} of entries) {
    const candidate = track?.candidate || take;
    const card = document.createElement("article");
    card.className = `card${track ? "" : " pending"}`;
    // Catalog content is inserted as text, never as markup.
    card.innerHTML = '<div class="card-top"><span class="provider-symbol"></span><span class="chip"></span></div><h3></h3><div class="model"></div>';
    card.querySelector(".provider-symbol").textContent = provider.local ? "∿" : "Ⅱ";
    const chip = card.querySelector(".chip");
    chip.textContent = provider.local ? "LOCAL MODEL" : provider.id === "gemini" ? "GEMINI" : provider.name.toUpperCase();
    chip.classList.toggle("cloud", !provider.local);
    card.querySelector("h3").textContent = compareVariants ? (track.title || `후보 ${candidate}`) : provider.name;
    const modelName = track?.model || provider.models?.[category] || provider.model;
    card.querySelector(".model").textContent = modelName === "eleven_text_to_sound_v2" ? "Sound Effects v2" : modelName;
    if (track?.processing_description || track?.description) {
      const description = document.createElement("p");
      description.className = "track-description";
      description.textContent = track.processing_description || track.description;
      card.append(description);
    }
    if (track?.acting_prompt) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "실제 연기 지시 보기";
      const prompt = document.createElement("p");
      prompt.className = "track-description";
      prompt.textContent = track.acting_prompt;
      details.append(summary, prompt);
      card.append(details);
    }
    if (track) {
      const line = document.createElement("div"); line.className = "track-line";
      const name = document.createElement("span"); name.className = "take-name"; name.textContent = `후보 ${candidate}`;
      const originalLabel = track.postprocessing ? "보정본" : "원본";
      const matchedLabel = Number.isFinite(track.matched_lufs) ? `비교 음량 (${track.matched_lufs.toFixed(1)} LUFS)` : "비교 음량";
      const detail = document.createElement("span"); detail.textContent = `${track.duration.toFixed(1)}초 · ${$("#matched").checked && track.matched ? matchedLabel : originalLabel}`;
      line.append(name, detail); card.append(line);
      const playbackName = ["voice-models", ...bossCategories].includes(category) ? `${track.model} 후보 ${candidate}` : category === "dialogue" && dialogueProcessing && provider.id === "gemini" ? `${provider.name} ${processingNames[track.dialogue_version]} 후보 ${candidate}` : `${provider.name} 후보 ${candidate}`;
      const audio = document.createElement("audio"); audio.controls = true; audio.preload = "metadata"; audio.src = source(track); audio.dataset.track = track.id;
      audio.setAttribute("aria-label", (category === "dialogue" && dialogueProcessing) || ["voice-models", ...bossCategories].includes(category) ? `${playbackName} ${title}` : `${provider.name} ${title} 후보 ${candidate}`); setupAudio(audio);
      const play = document.createElement("button"); play.className = "play-button"; play.textContent = "▶ 재생"; play.setAttribute("aria-label", `${playbackName} 재생`);
      play.addEventListener("click", () => { queue = []; sequenceActive = false; audio.loop = $("#loop").checked; if (audio.paused) audio.play().catch(() => status("재생하지 못했습니다. 음원 컨트롤에서 다시 시도해 주세요.")); else audio.pause(); });
      audio.addEventListener("play", () => { play.textContent = "Ⅱ 일시정지"; play.setAttribute("aria-label", `${playbackName} 일시정지`); });
      audio.addEventListener("pause", () => { play.textContent = "▶ 재생"; play.setAttribute("aria-label", `${playbackName} 재생`); });
      card.append(play, audio);
      const link = document.createElement("a"); link.className = "download"; link.href = track.original; link.download = `${track.id}.wav`; link.textContent = `${originalLabel} WAV 저장 ↗`; card.append(link);
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
$("#boss-language").addEventListener("change", () => {
  stopAll(); bossLanguage = $("#boss-language").value; render(); status("대사 언어를 바꿨습니다.");
});
$("#boss-direction").addEventListener("change", () => {
  stopAll(); bossDirection = $("#boss-direction").value; render(); status("연기 지시를 바꿨습니다.");
});
$("#boss-provider").addEventListener("change", () => {
  stopAll(); bossProvider = $("#boss-provider").value; render(); status("음성 제공자를 바꿨습니다.");
});
$("#dialogue-version").addEventListener("change", () => {
  stopAll(); dialogueVersion = $("#dialogue-version").value;
  saveDialogueSelection();
  render(); status(dialogueVersion === "neutral-retry" ? "A만 연기 지시 없이 재생성한 대조군입니다. B·C·D와 ElevenLabs는 기존 음원입니다." : "Gemini 비교 버전을 바꿨습니다. ElevenLabs 비교 음원은 같습니다.");
});
$("#dialogue-processing").addEventListener("change", () => {
  stopAll(); dialogueProcessing = $("#dialogue-processing").checked;
  saveDialogueSelection(); render();
  status(dialogueProcessing ? "같은 감정의 원본과 여러 보정본을 한눈에 비교합니다." : "선택한 버전의 네 가지 감정을 비교합니다.");
});
$("#dialogue-line").addEventListener("change", () => {
  stopAll(); dialogueLine = $("#dialogue-line").value;
  saveDialogueSelection(); render(); status(`${$("#dialogue-line").selectedOptions[0].textContent} 보정본을 비교합니다.`);
});
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
