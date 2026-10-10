/* 实际站心数据的双半球绘图组件；坐标与星等来自后端。 */
"use strict";
(() => {
  const starAliases = {Sirius:"天狼星",Polaris:"北极星",Vega:"织女星",Altair:"河鼓二",Deneb:"天津四",Betelgeuse:"参宿四",Rigel:"参宿七",Aldebaran:"毕宿五",Arcturus:"大角星",Capella:"五车二",Antares:"心宿二",Spica:"角宿一",Pollux:"北河三",Castor:"北河二",Fomalhaut:"北落师门",Canopus:"老人星",Regulus:"轩辕十四"};
  const constellationAliases = {Ori:"猎户座",Sco:"天蝎座",Cas:"仙后座",UMa:"大熊座",UMi:"小熊座",Cyg:"天鹅座",Aql:"天鹰座",Lyr:"天琴座",Dra:"天龙座",Ari:"白羊座",Tau:"金牛座",Gem:"双子座",Cnc:"巨蟹座",Leo:"狮子座",Vir:"室女座",Lib:"天秤座",Sgr:"人马座",Cap:"摩羯座",Aqr:"宝瓶座",Psc:"双鱼座",Oph:"蛇夫座",Per:"英仙座",And:"仙女座",Peg:"飞马座",Cru:"南十字座"};
  const indexes = new WeakMap();
  const controls = new WeakMap();
  const starName = (star) => starAliases[star.name] || star.name || `HIP ${star.hip}`;
  function style(magnitude) {
    if(magnitude===null)return {radius:2,alpha:.6,unknown:true};
    return {radius:.65+3.85/(1+Math.exp((magnitude-.5)/1.5)),alpha:.22+.78/(1+Math.exp((magnitude-1.5)/2))};
  }
  function label(ctx,text,x,y,color,reserved,size=11,force=false) {
    ctx.font=`${size}px "Segoe UI","Microsoft YaHei",sans-serif`;
    const width=ctx.measureText(text).width;
    const candidates=[[9,-9],[9,17],[-width-10,-9],[-width-10,17],[8,-23]];
    let chosen=null;
    for(const [dx,dy] of candidates) {
      const rect={x:x+dx-2,y:y+dy-size-2,w:width+4,h:size+5};
      if(rect.x<3 || rect.x+rect.w>ctx.canvas.clientWidth-3 || rect.y<3 || rect.y+rect.h>ctx.canvas.clientWidth-16)continue;
      if(reserved.every(other=>rect.x+rect.w<other.x || other.x+other.w<rect.x || rect.y+rect.h<other.y || other.y+other.h<rect.y)) {chosen=[dx,dy,rect];break;}
    }
    if(!chosen && !force)return;
    chosen=chosen || [9,-9,{x:x+7,y:y-size-11,w:width+4,h:size+5}];
    reserved.push(chosen[2]);
    ctx.lineWidth=3;ctx.strokeStyle="#09131cf0";ctx.strokeText(text,x+chosen[0],y+chosen[1]);
    ctx.fillStyle=color;ctx.fillText(text,x+chosen[0],y+chosen[1]);
  }
  function render(canvas,data,hemisphere,options={}) {
    const scene=data.hemispheres[hemisphere];
    const width=canvas.clientWidth || 560,height=width;
    const dpr=Math.min(devicePixelRatio || 1,3);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);
    const cx=width/2,cy=height/2,radius=width*.405;
    const accent=hemisphere==="upper"?"#8bd9c1":"#c1acd7";
    ctx.fillStyle=hemisphere==="upper"?"#0c1a25":"#151722";ctx.fillRect(0,0,width,height);
    const gradient=ctx.createRadialGradient(cx,cy,0,cx,cy,radius);
    gradient.addColorStop(0,hemisphere==="upper"?"#132735":"#232133");gradient.addColorStop(1,"#0c1420");
    ctx.fillStyle=gradient;ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle=hemisphere==="upper"?"#34544d":"#51445d";ctx.lineWidth=1;
    [1/3,2/3,1].forEach(f=>{ctx.beginPath();ctx.arc(cx,cy,radius*f,0,Math.PI*2);ctx.stroke();});
    ctx.strokeStyle="#8daaaa25";
    for(let angle=0;angle<360;angle+=30){const a=angle*Math.PI/180;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+radius*Math.sin(a),cy-radius*Math.cos(a));ctx.stroke();}
    ctx.font='11px "Microsoft YaHei",sans-serif';ctx.fillStyle="#8b9dabb0";
    [30,60].forEach(alt=>{const distance=(90-alt)/90*radius;ctx.fillText(`${hemisphere==="upper"?"":"−"}${alt}°`,cx+4,cy-distance+12);});
    ctx.textAlign="center";ctx.font='13px "Microsoft YaHei",sans-serif';ctx.fillStyle=accent;
    ctx.fillText("北",cx,cy-radius-18);ctx.fillText("南",cx,cy+radius+27);
    ctx.fillText(hemisphere==="upper"?"东":"西",cx-radius-25,cy+5);
    ctx.fillText(hemisphere==="upper"?"西":"东",cx+radius+25,cy+5);
    ctx.font='10px "Microsoft YaHei",sans-serif';ctx.fillStyle="#adc4d050";
    ctx.fillText(hemisphere==="upper"?"天顶":"天底",cx,cy+18);ctx.textAlign="left";
    const point=xy=>[cx+xy[0]*radius,cy+xy[1]*radius];
    const reserved=[{x:cx-17,y:cy+7,w:35,h:14}],hit=[];
    ctx.save();ctx.beginPath();ctx.arc(cx,cy,radius-.1,0,Math.PI*2);ctx.clip();
    if(options.lines!==false) {
      ctx.strokeStyle=hemisphere==="upper"?"#739dc96b":"#ad8ccd65";ctx.lineWidth=.8;
      scene.constellations.forEach(group=>group.lines.forEach(line=>{
        ctx.beginPath();line.forEach((xy,i)=>{const p=point(xy);if(i)ctx.lineTo(...p);else ctx.moveTo(...p);});ctx.stroke();
      }));
    }
    const stars=[...scene.stars].sort((a,b)=>b.magnitude-a.magnitude);
    stars.forEach(star=>{
      const [x,y]=point(star.xy),visual=style(star.magnitude);
      ctx.globalAlpha=visual.alpha;
      if(star.magnitude<1){const glow=ctx.createRadialGradient(x,y,0,x,y,visual.radius*3);glow.addColorStop(0,"#e4ecff60");glow.addColorStop(1,"#e4ecff00");ctx.fillStyle=glow;ctx.beginPath();ctx.arc(x,y,visual.radius*3,0,Math.PI*2);ctx.fill();}
      ctx.fillStyle="#e2ebf7";ctx.beginPath();ctx.arc(x,y,visual.radius,0,Math.PI*2);ctx.fill();
      hit.push({x,y,object:{...star,kind:"star",display_name:starName(star)}});
    });
    ctx.globalAlpha=1;
    const planetLabels=[];
    scene.planets.forEach(planet=>{
      const [x,y]=point(planet.xy),visual=style(planet.magnitude);
      const glow=ctx.createRadialGradient(x,y,0,x,y,Math.max(5,visual.radius*3));
      glow.addColorStop(0,`rgba(253,216,154,${visual.alpha*.45})`);glow.addColorStop(1,"rgba(253,216,154,0)");
      ctx.fillStyle=glow;ctx.beginPath();ctx.arc(x,y,Math.max(5,visual.radius*3),0,Math.PI*2);ctx.fill();
      ctx.globalAlpha=visual.alpha;ctx.fillStyle="#ffdea2";ctx.strokeStyle="#dcbf84";
      ctx.beginPath();ctx.arc(x,y,visual.radius,0,Math.PI*2);if(visual.unknown)ctx.stroke();else ctx.fill();
      ctx.globalAlpha=1;ctx.strokeStyle="#f3d997a0";ctx.lineWidth=.7;
      ctx.beginPath();ctx.arc(x,y,Math.max(6,visual.radius+2),0,Math.PI*2);ctx.stroke();
      planetLabels.push([planet,x,y]);hit.push({x,y,object:{...planet,kind:"planet",display_name:planet.name}});
    });
    scene.references.forEach(reference=>{
      const [x,y]=point(reference.xy);ctx.strokeStyle="#dcbd71";ctx.lineWidth=1.2;
      ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.stroke();
      for(let a=0;a<Math.PI*2;a+=Math.PI/4){ctx.beginPath();ctx.moveTo(x+8*Math.cos(a),y+8*Math.sin(a));ctx.lineTo(x+11*Math.cos(a),y+11*Math.sin(a));ctx.stroke();}
      label(ctx,"太阳方位",x,y,"#ebd89e",reserved,11,true);
      hit.push({x,y,object:{...reference,kind:"reference",display_name:"太阳方位参考"}});
    });
    ctx.restore();
    planetLabels.forEach(([planet,x,y])=>label(ctx,planet.name,x,y,"#ffe4ad",reserved,12,true));
    if(options.names!==false){
      [...scene.stars].filter(star=>star.name && star.magnitude<=(width<380?2:3.3)).sort((a,b)=>a.magnitude-b.magnitude).slice(0,width<380?12:35).forEach(star=>{const [x,y]=point(star.xy);label(ctx,starName(star),x,y,"#c6d8ef",reserved,10);});
    }
    if(options.lines!==false && options.constellationNames!==false){
      [...scene.constellations].sort((a,b)=>b.lines.length-a.lines.length).slice(0,width<380?10:88).forEach(group=>{
        const points=group.lines.flat();if(points.length<6)return;
        const mean=points.reduce((sum,p)=>[sum[0]+p[0]/points.length,sum[1]+p[1]/points.length],[0,0]);
        const [x,y]=point(mean);label(ctx,constellationAliases[group.abbr] || group.name,x,y,"#8eabc58f",reserved,10);
      });
    }
    ctx.textAlign="center";ctx.font='9px "Segoe UI",sans-serif';ctx.fillStyle="#829aa2";
    ctx.fillText(width<380?"Hipparcos · JPL · S&T / CC BY-SA 2.0":"Hipparcos · JPL · 星座线 Stellarium S&T / CC BY-SA 2.0",cx,height-8);ctx.textAlign="left";
    indexes.set(canvas,{points:hit,cx,cy,radius,width,data,hemisphere});
    return {stars:scene.stars.length,planets:scene.planets.length};
  }
  function pick(canvas,event) {
    const index=indexes.get(canvas);if(!index)return null;
    const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
    return index.points.filter(item=>Math.hypot(item.x-x,item.y-y)<Math.max(7,item.object.kind==="planet"?11:7))
      .sort((a,b)=>(a.object.kind==="planet"?-1:0)-(b.object.kind==="planet"?-1:0) || (a.object.magnitude??20)-(b.object.magnitude??20))[0]?.object || null;
  }
  function bind(canvas,callback) {
    if(controls.has(canvas))return;
    const listener=event=>callback(pick(canvas,event));
    canvas.addEventListener("pointermove",listener);canvas.addEventListener("click",listener);
    canvas.addEventListener("pointerleave",()=>callback(null));controls.set(canvas,listener);
  }
  function exportImage(data,options={}) {
    const output=document.createElement("canvas");output.width=1680;output.height=1000;
    const ctx=output.getContext("2d");ctx.fillStyle="#101b25";ctx.fillRect(0,0,1680,1000);
    ctx.font='28px "Microsoft YaHei",sans-serif';ctx.fillStyle="#dcf0e8";ctx.fillText("星图",38,45);
    ctx.font='15px "Microsoft YaHei",sans-serif';ctx.fillStyle="#a3b8bc";ctx.fillText(`${data.site.label} · ${data.epoch_local} · 纬度 ${data.site.latitude}° / 经度 ${data.site.longitude}°`,38,76);
    ["upper","lower"].forEach((hemisphere,index)=>{
      const canvas=document.createElement("canvas");Object.defineProperty(canvas,"clientWidth",{value:800});
      render(canvas,data,hemisphere,options);ctx.drawImage(canvas,30+index*830,120,800,800);
      ctx.fillStyle=hemisphere==="upper"?"#a6dfcc":"#d3bce5";ctx.font='18px "Microsoft YaHei",sans-serif';ctx.fillText(hemisphere==="upper"?"上半球 · 天顶中心 / 地平线以上":"暗面 · 天底中心 / 地球遮挡",44+index*830,108);
    });
    ctx.font='13px "Microsoft YaHei",sans-serif';ctx.fillStyle="#9aadba";
    ctx.fillText("理想水平地平线、无折射；星等经曝光映射。星座图形：Paul Krizak, Jonathan E. Piskor, G. Zotti / Stellarium Sky & Telescope · CC BY-SA 2.0",38,949,1600);
    ctx.fillText("数据：ESA Hipparcos (CDS I/239) · NASA/JPL DE440s · GeoNames (CC BY 4.0) · 图形来源 github.com/Stellarium/stellarium/tree/master/skycultures/modern_st",38,976,1600);
    return output;
  }
  window.AstroSky={render,bind,style,exportImage};
})();
