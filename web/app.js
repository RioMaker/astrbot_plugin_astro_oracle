"use strict";
const $ = (id) => document.getElementById(id);
let current = null;
let sampleIndex = 0;
let selectedPlanet = "mercury";
let pending = false;
const colors = {mercury:"#cdbda3",venus:"#e3c47c",earth:"#83c2d1",mars:"#dba28b",jupiter:"#dabba0",saturn:"#d6cf9b",uranus:"#98d2cd",neptune:"#8ba9d0"};
const format = (number, digits = 6) => number === null || number === undefined ? "—" : number.toFixed(digits);
const localLabel = (value) => value.replace("T", " ");
function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}
function invalidate() {
  current = null;
  $("results").hidden = true;
  $("error").hidden = true;
  $("query-status").textContent = "输入已更新，请重新计算。";
  updateHint();
}
function updateHint() {
  const value = $("input-time").value.trim();
  const match = /^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2})(?::(\d{2})(?::(\d{2}))?)?)?$/.exec(value);
  const precision = !match ? null : match[4] ? "second" : match[3] ? "minute" : match[2] ? "hour" : "day";
  const hints = {day:"日精度 · 计算全天多个采样时刻",hour:"时精度 · 计算这一小时内的多个时刻",minute:"分精度 · 计算这一分钟内的多个时刻",second:"秒精度 · 计算指定时刻，不额外假设小数秒"};
  $("precision-hint").textContent = hints[precision] || "支持 YYYY-MM-DD，或追加 HH、HH:MM、HH:MM:SS";
  $("samples").disabled = precision === "second" || pending;
}
function renderVectors(id, values, labels, digits) {
  $(id).replaceChildren();
  values.forEach((value, index) => {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = labels[index];
    const dd = document.createElement("dd");
    dd.textContent = format(value, digits);
    row.append(dt, dd);
    $(id).append(row);
  });
}
function renderDetail() {
  const snapshot = current.snapshots[sampleIndex];
  const body = snapshot.planets.find((planet) => planet.key === selectedPlanet);
  $("planet-select").value = selectedPlanet;
  $("detail-title").textContent = `${body.name} · 位置与速度`;
  $("target-note").textContent = `NAIF ${body.naif_id} · ${body.target_kind === "body_center" ? "行星本体中心" : "行星系统质心，包含卫星系统的质心效应"}`;
  renderVectors("position-vector", body.heliocentric.position_au, ["X", "Y", "Z"], 10);
  renderVectors("velocity-vector", body.heliocentric.velocity_km_s, ["VX", "VY", "VZ"], 8);
  const geo = body.geocentric_apparent;
  renderVectors("equatorial", geo ? [geo.right_ascension_deg, geo.declination_deg] : [null,null], ["赤经", "赤纬"], 8);
  $("trend-title").textContent = current.window.mode === "instant" ? `${body.name} · 指定时刻` : `${body.name} · 时段采样变化`;
  $("trend-rows").replaceChildren();
  current.snapshots.forEach((item) => {
    const planet = item.planets.find((value) => value.key === selectedPlanet);
    const row = document.createElement("tr");
    const apparent = planet.geocentric_apparent;
    row.append(cell(localLabel(item.local_time)),cell(format(apparent?.ecliptic_longitude_deg)),cell(format(apparent?.ecliptic_latitude_deg)),cell(format(apparent?.distance_au,8)),cell(format(planet.heliocentric.distance_au,8)),cell(format(planet.heliocentric.speed_km_s)));
    $("trend-rows").append(row);
  });
  $("resolution-note").textContent = current.window.sampling_note;
}
function renderSnapshot() {
  const snapshot = current.snapshots[sampleIndex];
  $("selected-time").textContent = localLabel(snapshot.local_time);
  $("selected-utc").textContent = `UTC ${localLabel(snapshot.utc)} · TDB JD ${snapshot.tdb_jd.toFixed(9)}`;
  $("sample-tabs").querySelectorAll("button").forEach((button,index) => {
    button.classList.toggle("active", index === sampleIndex);
    button.setAttribute("aria-pressed", String(index === sampleIndex));
  });
  $("planet-rows").replaceChildren();
  snapshot.planets.forEach((body) => {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    const dot = document.createElement("span"); dot.className="dot"; dot.style.background=colors[body.key];
    label.append(dot,document.createTextNode(body.name));
    const kind = document.createElement("small");
    kind.textContent = body.target_kind === "body_center" ? "本体中心" : "行星系统质心";
    label.append(kind);
    const geo = body.geocentric_apparent;
    row.append(label,cell(format(body.heliocentric.distance_au,8)),cell(format(body.heliocentric.speed_km_s)),cell(format(geo?.ecliptic_longitude_deg)),cell(format(geo?.ecliptic_latitude_deg)),cell(format(geo?.distance_au,8)));
    const control = document.createElement("button"); control.className="row-detail"; control.type="button";
    control.textContent="查看"; control.setAttribute("aria-label", `查看${body.name}详情`);
    control.addEventListener("click",() => { selectedPlanet=body.key; renderDetail(); });
    const detail = document.createElement("td"); detail.append(control); row.append(detail);
    $("planet-rows").append(row);
  });
  renderDetail();
}
function renderResult() {
  const window = current.window;
  $("window-title").textContent = `${window.original} · ${window.precision_label}精度`;
  $("window-range").textContent = window.mode === "instant" ? `指定时刻 ${localLabel(window.start_local)} · ${window.timezone}` : `${localLabel(window.start_local)} 至 ${localLabel(window.end_local_exclusive)}（终点不包含）`;
  $("sample-note").textContent = `${current.sample_count} 个采样 · ${window.mode === "instant" ? "指定秒" : `实际跨度 ${window.elapsed_seconds.toLocaleString()} 秒`}`;
  $("sample-tabs").replaceChildren();
  current.snapshots.forEach((snapshot,index) => {
    const button = document.createElement("button"); button.type="button";
    button.textContent = snapshot.local_time.slice(11,19);
    button.addEventListener("click",() => {sampleIndex=index;renderSnapshot();});
    $("sample-tabs").append(button);
  });
  $("planet-select").replaceChildren();
  current.snapshots[0].planets.forEach((planet) => {
    const option = document.createElement("option"); option.value=planet.key;option.textContent=planet.name;
    $("planet-select").append(option);
  });
  $("provenance").replaceChildren();
  [...Object.values(current.definitions),...current.notes].forEach((text) => {
    const paragraph = document.createElement("p");paragraph.textContent=text;$("provenance").append(paragraph);
  });
  $("provenance-json").textContent=JSON.stringify(current.provenance,null,2);
  $("results").hidden=false;
  renderSnapshot();
}
$("state-form").addEventListener("submit",async(event) => {
  event.preventDefault();
  if(pending)return;
  pending=true;
  $("calculate").disabled=true;
  $("input-time").disabled=true;
  $("timezone").disabled=true;
  $("error").hidden=true;
  $("results").hidden=true;
  $("query-status").textContent="正在读取本地历表并计算…";
  updateHint();
  try {
    const response=await fetch("/api/state",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({time:$("input-time").value,timezone:$("timezone").value,samples:Number($("samples").value)})});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error || "计算失败。");
    current=data;sampleIndex=0;
    renderResult();
    $("query-status").textContent=`计算完成 · ${data.sample_count} 个时刻 × 8 个行星状态 · 本地 JPL DE440s`;
  } catch(error) {
    current=null;
    $("error").textContent=error.message;
    $("error").hidden=false;
    $("query-status").textContent="本次计算未完成，请检查输入。";
  } finally {
    pending=false;
    $("calculate").disabled=false;
    $("input-time").disabled=false;
    $("timezone").disabled=false;
    updateHint();
  }
});
$("planet-select").addEventListener("change",() => {selectedPlanet=$("planet-select").value;renderDetail();});
[$("input-time"),$("timezone"),$("samples")].forEach((element) => element.addEventListener("input",invalidate));
document.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click",() => {
  if(pending)return;
  const date=/^\d{4}-\d{2}-\d{2}/.exec($("input-time").value)?.[0] || "2026-10-09";
  const suffix={day:"",hour:" 12",minute:" 12:34",second:" 12:34:56"};
  $("input-time").value=date+suffix[button.dataset.preset];invalidate();
}));
$("export-json").addEventListener("click",() => {
  if(!current)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:"application/json"}));
  const link=document.createElement("a");link.href=url;link.download=`astro-oracle-${current.window.original.replace(/[^0-9]/g,"")}.json`;link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
});
async function loadInfo() {
  try {
    const response=await fetch("/api/info");
    if(!response.ok)throw new Error("历表信息加载失败。");
    const info=await response.json();
    $("model-status").textContent="JPL DE440s · 本地已就绪";
    $("coverage").textContent=`当前文件覆盖（UTC 换算）：${localLabel(info.coverage.start_utc)} 至 ${localLabel(info.coverage.end_utc)}。超出范围会明确提示。`;
  } catch(error) {$("model-status").textContent="本地服务未就绪";$("coverage").textContent=error.message;}
}
updateHint();
loadInfo();
