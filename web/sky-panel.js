"use strict";
(() => {
  const $=id=>document.getElementById(id);
  let current=null,lastSnapshot=null,lastWindow=null,requestVersion=0,controller=null,busy=false;
  const cache=new Map();
  const options=()=>({lines:$("show-lines").checked,names:$("show-star-names").checked,constellationNames:$("show-constellation-names").checked});
  function site() {return {latitude:Number($("latitude").value),longitude:Number($("longitude").value),elevation_m:Number($("elevation").value),label:$("place-label").value};}
  function describe(object,hemisphere) {
    const target=$("sky-detail");
    if(!object){target.textContent="移动指针或点击星点，查看名称、星等、方位角和视高度。";return;}
    const identity=object.kind==="star"?`HIP ${object.hip}`:object.kind==="planet"?`NAIF ${object.naif_id}`:"方位参考";
    const magnitude=object.magnitude===undefined?"参考符号":object.magnitude===null?"当前条件下星等未知":`视星等 ${object.magnitude.toFixed(2)}`;
    target.textContent=`${object.display_name} · ${identity} · ${magnitude} · 方位 ${object.azimuth_deg.toFixed(3)}° · 视高度 ${object.altitude_deg.toFixed(3)}° · ${hemisphere==="upper"?"地平线以上":"地球遮挡的下半球"}`;
  }
  function draw() {
    if(!current)return;
    for(const hemisphere of ["upper","lower"]){
      AstroSky.render($("sky-"+hemisphere),current,hemisphere,options());
      const scene=current.hemispheres[hemisphere];
      $(hemisphere+"-counts").textContent=`${scene.stars.length.toLocaleString()} 颗恒星 · ${scene.planets.length} 个行星目标`;
      $(hemisphere+"-planets").textContent=scene.planets.map(p=>`${p.name} ${p.magnitude===null?"星等未知":p.magnitude.toFixed(2)+" 等"}`).join(" / ") || "此半球当前没有可绘制的行星目标";
    }
  }
  function invalidate() {
    requestVersion++;
    controller?.abort();
    current=null;lastSnapshot=null;lastWindow=null;cache.clear();
    $("sky-empty").hidden=false;$("sky-plots").hidden=true;
    $("sky-status").textContent="输入时间和出生地后生成双半球星图。";
    $("export-sky-png").disabled=true;$("export-sky-json").disabled=true;
  }
  async function setSnapshot(snapshot,window) {
    lastSnapshot=snapshot;lastWindow=window;
    const version=++requestVersion;
    controller?.abort();controller=new AbortController();
    const parameters={epoch:snapshot.utc,site:site(),timezone:window.timezone,magnitude_limit:Number($("mag-limit").value)};
    const key=JSON.stringify(parameters);
    $("sky-status").textContent="正在计算出生地的站心方向与两个半球…";
    $("sky-plots").hidden=true;$("sky-empty").hidden=false;
    $("export-sky-png").disabled=true;$("export-sky-json").disabled=true;
    try {
      let data=cache.get(key);
      if(!data){
        const response=await fetch("/api/sky",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(parameters),signal:controller.signal});
        data=await response.json();if(!response.ok)throw new Error(data.error || "星图计算失败。");
        cache.set(key,data);if(cache.size>16)cache.delete(cache.keys().next().value);
      }
      if(version!==requestVersion)return;
      current=data;
      $("sky-empty").hidden=true;$("sky-plots").hidden=false;
      $("sky-stamp").textContent=`${data.site.label} · ${data.epoch_local.replace("T"," ")}`;
      const condition={day:"当地昼间",twilight:"当地晨昏",night:"当地夜间"}[data.sky_condition];
      $("sky-status").textContent=`双半球星图已就绪 · ${condition} · 太阳视高度 ${data.sun_altitude_deg.toFixed(2)}°`;
      $("sky-visibility-note").textContent=`${condition}。图中表示理想地平线划分的天体方向；肉眼可见性还受日光、地形、天气与仪器影响。`;
      $("sky-provenance").textContent=JSON.stringify({site:data.site,epoch_utc:data.epoch_utc,projection:data.projection,notes:data.notes,missing_constellation_edges:data.missing_constellation_edges,provenance:data.provenance},null,2);
      $("export-sky-png").disabled=false;$("export-sky-json").disabled=false;
      draw();
    }catch(error){
      if(error.name==="AbortError" || version!==requestVersion)return;
      current=null;$("sky-status").textContent=error.message;
    }
  }
  async function searchPlaces() {
    const query=$("place-query").value.trim();if(!query)return;
    $("search-places").disabled=true;$("place-results").replaceChildren();
    $("place-search-status").textContent="正在检索本地地名…";
    try {
      const response=await fetch("/api/places?q="+encodeURIComponent(query));
      const data=await response.json();if(!response.ok)throw new Error(data.error);
      data.results.forEach(place=>{
        const button=document.createElement("button");button.type="button";button.className="place-option";button.disabled=busy;
        button.textContent=`${place.name} · ${place.country} · ${place.timezone}`;
        button.addEventListener("click",()=>{
          $("latitude").value=place.latitude;$("longitude").value=place.longitude;
          $("elevation").value=0;$("place-label").value=`${place.name} / ${place.country}`;
          if(place.timezone)$("timezone").value=place.timezone;
          $("timezone").dispatchEvent(new Event("input"));
          $("place-search-status").textContent=`已选择 ${place.name}，坐标为城市/乡镇中心，可手动校正。`;
          $("place-results").replaceChildren();
        });
        $("place-results").append(button);
      });
      $("place-search-status").textContent=data.results.length?"选择结果后可校正经纬度、观测点高度与输入时间的时区。":"本地库没有找到该名称，可改用城市/乡镇关键词，或直接填写经纬度。";
    }catch(error){$("place-search-status").textContent=error.message;}
    finally{$("search-places").disabled=false;}
  }
  function init(info) {
    const place=info?.example_site;
      if(place && !$("latitude").value && !$("longitude").value){
      $("latitude").value=place.latitude;$("longitude").value=place.longitude;
      $("place-label").value=`${place.name}（调试示例）`;
    }
    $("sky-resource-info").textContent=`本地星图资源：${info.star_count.toLocaleString()} 颗适用恒星 · ${info.constellation_count} 个星座条目 · ${info.city_count.toLocaleString()} 个城市/乡镇`;
  }
  $("search-places").addEventListener("click",searchPlaces);
  $("place-query").addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();searchPlaces();}});
  ["latitude","longitude","elevation","place-label"].forEach(id=>$(id).addEventListener("input",()=>$("timezone").dispatchEvent(new Event("input"))));
  ["show-lines","show-star-names","show-constellation-names"].forEach(id=>$(id).addEventListener("change",draw));
  $("mag-limit").addEventListener("input",()=>$("mag-value").textContent=Number($("mag-limit").value).toFixed(1));
  $("mag-limit").addEventListener("change",()=>{if(lastSnapshot)setSnapshot(lastSnapshot,lastWindow);});
  ["upper","lower"].forEach(hemisphere=>AstroSky.bind($("sky-"+hemisphere),object=>describe(object,hemisphere)));
  new ResizeObserver(()=>{if(current)requestAnimationFrame(draw);}).observe($("sky-panel"));
  $("export-sky-png").addEventListener("click",()=>{
    if(!current)return;
    AstroSky.exportImage(current,options()).toBlob(blob=>{
      const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download="astro-oracle-dual-sky.png";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    },"image/png");
  });
  $("export-sky-json").addEventListener("click",()=>{
    if(!current)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download="astro-oracle-dual-sky.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  function setBusy(value) {
    busy=value;
    ["latitude","longitude","elevation","place-label","place-query","search-places"].forEach(id=>$(id).disabled=value);
    $("place-results").querySelectorAll("button").forEach(button=>button.disabled=value);
  }
  window.SkyPanel={init,invalidate,setSnapshot,setBusy};
})();
