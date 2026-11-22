"""
کامپوننت چارت: Lightweight Charts v4 + WebSocket
- کندل زنده + حجم + هدر (پایانی/آخرین/صف)
- پنل‌های جداگانه برای اندیکاتورهای غیر overlay، هم‌زمان‌سازی محور زمان
- خطوط (plots)، سطوح (levels)، باکس‌ها (zones: OB / S&D / S/R / MP)، خطوط افقی (lines: Liq / PDH …)
- مارکرهای سیگنال با استایل هر اندیکاتور، نوتیف سیگنال جدید
- لِجند OHLCV روی کراس‌هر، reconnect خودکار
"""

_TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  html,body{margin:0;height:100%;background:#131722;color:#d1d4dc;font-family:Vazirmatn,Tahoma,sans-serif;overflow:hidden}
  #hdr{height:34px;padding:0 12px;display:flex;gap:18px;align-items:center;font-size:13px;border-bottom:1px solid #2a2e39;white-space:nowrap}
  #hdr b{font-size:14px} .k{color:#9aa0a6;font-size:11px;margin-left:4px}
  .up{color:#26a69a} .dn{color:#ef5350}
  #st{margin-left:auto;font-size:11px;color:#9aa0a6}
  #st.sig{color:#ffd54f;font-weight:bold}
  .pane{position:relative;border-top:1px solid #2a2e39}
  .lbl{position:absolute;top:4px;left:8px;z-index:5;font-size:11px;color:#9aa0a6;pointer-events:none;line-height:1.5}
  .lbl span{margin-right:8px}
</style></head>
<body>
<div id="hdr">
  <b id="sym">—</b>
  <span><span class="k">پایانی</span><b id="fin">—</b> <span id="finp"></span></span>
  <span><span class="k">آخرین</span><b id="lst">—</b> <span id="lstp"></span></span>
  <span id="q"></span>
  <span id="st">connecting…</span>
</div>
<div id="root"></div>

<script>
const WS_URL = "__WS_URL__", H = __HEIGHT__;
const HDR_H = 34;
const OPTS = {
  layout:{background:{color:'#131722'},textColor:'#d1d4dc',fontFamily:'Vazirmatn,Tahoma,sans-serif'},
  grid:{vertLines:{color:'#1e222d'},horzLines:{color:'#1e222d'}},
  timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#2a2e39',rightOffset:5},
  rightPriceScale:{borderColor:'#2a2e39'},
  crosshair:{mode:0},
  localization:{locale:'en-US'}
};
const LINE_STYLE = {solid:0, dotted:1, dashed:2, large_dashed:3, sparse_dotted:4};

let charts = [], series = {}, main = null, candle = null, vol = null, legend = null, boxes = null;
const W = () => document.body.clientWidth;
const fmt = v => Math.round(v || 0).toLocaleString();
const pct = v => ((v || 0) >= 0 ? '+' : '') + (v || 0).toFixed(2) + '%';

/* ───── Box primitive: مستطیل بین دو قیمت و دو زمان (معادل box در Pine) ───── */
class Boxes {
  constructor(zones){ this.z = zones; this._views = [{zOrder:()=>'bottom', renderer:()=>({draw:t=>this.draw(t)})}]; }
  attached({chart, series}){ this.chart = chart; this.series = series; }
  detached(){} updateAllViews(){} paneViews(){ return this._views; }
  setZones(z){ this.z = z; }
  draw(target){
    target.useMediaCoordinateSpace(({context:ctx, mediaSize}) => {
      const ts = this.chart.timeScale(), vr = ts.getVisibleRange(); if(!vr) return;
      for(const z of this.z){
        const zto = z.extend ? Infinity : z.to;
        if(zto < vr.from || z.from > vr.to) continue;
        let x1 = ts.timeToCoordinate(z.from); if(x1 === null) x1 = z.from < vr.from ? 0 : null;
        let x2 = z.extend ? mediaSize.width : ts.timeToCoordinate(z.to);
        if(x2 === null) x2 = z.to > vr.to ? mediaSize.width : null;
        if(x1 === null || x2 === null) continue;
        const y1 = this.series.priceToCoordinate(z.top), y2 = this.series.priceToCoordinate(z.btm);
        if(y1 === null || y2 === null) continue;
        ctx.fillStyle = z.color; ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
        ctx.strokeStyle = z.color.replace(/[\d.]+\)$/, '0.6)'); ctx.lineWidth = 1;
        ctx.strokeRect(x1 + .5, y1 + .5, x2 - x1 - 1, y2 - y1 - 1);
        if(z.label){ ctx.fillStyle = '#d1d4dc'; ctx.font = '10px Tahoma'; ctx.fillText(z.label, x1 + 4, y1 + 11); }
      }
    });
  }
}

/* ───── ساخت pane ها ───── */
function clearAll(){
  charts.forEach(c => c.remove()); charts = []; series = {}; main = candle = vol = legend = boxes = null;
  document.getElementById('root').innerHTML = '';
}
function mkPane(h, label){
  const d = document.createElement('div'); d.className = 'pane'; d.style.height = h + 'px';
  const l = document.createElement('div'); l.className = 'lbl'; l.innerHTML = '<span>' + label + '</span>'; d.appendChild(l);
  document.getElementById('root').appendChild(d);
  const c = LightweightCharts.createChart(d, {...OPTS, width: W(), height: h});
  charts.push(c); return {chart: c, label: l};
}
function syncTime(){
  charts.forEach(src => src.timeScale().subscribeVisibleLogicalRangeChange(r => {
    if(!r) return; charts.forEach(o => { if(o !== src) o.timeScale().setVisibleLogicalRange(r); });
  }));
}
function addHLine(ch, ln, overlayOnMain){
  const style = LINE_STYLE[ln.style] ?? 0;
  if(!(ln.from < ln.to)){                       // خط بی‌نهایت
    candle.createPriceLine({price: ln.price, color: ln.color, lineStyle: style, lineWidth: 1, axisLabelVisible: true, title: ln.label || ''});
    return;
  }
  const ls = (overlayOnMain ? main : ch).addLineSeries({color: ln.color, lineWidth: 1, lineStyle: style, title: ln.label || '',
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false});
  ls.setData([{time: ln.from, value: ln.price}, {time: ln.to, value: ln.price}]);
}

/* ───── init ───── */
function build(m){
  clearAll();
  const subs = m.panes.filter(p => !p.overlay);
  const subH = subs.length ? Math.min(160, Math.floor(H * 0.42 / subs.length)) : 0;
  const mainH = H - HDR_H - subH * subs.length;

  const mp = mkPane(mainH, (m.meta.symbol || '') + ' · ' + m.config.timeframe);
  main = mp.chart; legend = mp.label;
  candle = main.addCandlestickSeries({upColor:'#26a69a', downColor:'#ef5350', borderVisible:false, wickUpColor:'#26a69a', wickDownColor:'#ef5350'});
  candle.setData(m.candles);
  vol = main.addHistogramSeries({priceFormat:{type:'volume'}, priceScaleId:'vol', lastValueVisible:false, priceLineVisible:false});
  main.priceScale('vol').applyOptions({scaleMargins:{top:0.82, bottom:0}});
  vol.setData(m.volume);

  const zones = [];
  let palette = 0;
  m.panes.forEach(p => {
    const pane = p.overlay ? {chart: main} : mkPane(subH, p.id);
    const ch = pane.chart; series[p.id] = {};
    (p.series || []).forEach(s => {
      const ls = ch.addLineSeries({color: s.color, lineWidth: 1.5, title: s.name, priceLineVisible: false, lastValueVisible: !p.overlay});
      ls.setData(s.data); series[p.id][s.name] = ls;
    });
    const first = Object.values(series[p.id])[0];
    if(first && !p.overlay) (p.levels || []).forEach(v =>
      first.createPriceLine({price: v, color: '#787b86', lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: ''}));
    (p.lines || []).forEach(ln => addHLine(ch, ln, p.overlay));
    if(p.overlay) zones.push(...(p.zones || []));
  });
  if(zones.length){ boxes = new Boxes(zones); candle.attachPrimitive(boxes); }

  candle.setMarkers(m.markers || []);
  syncTime();
  charts.forEach(c => c.timeScale().fitContent());
  main.subscribeCrosshairMove(onCrosshair);
  hdr(m.meta);
}

/* ───── update ───── */
function update(m){
  if(!candle) return;
  if(m.candle) candle.update(m.candle);
  if(m.volume) vol.update(m.volume);
  Object.entries(m.points || {}).forEach(([pid, ss]) => Object.entries(ss).forEach(([n, pt]) => {
    if(series[pid] && series[pid][n] && pt) series[pid][n].update(pt);
  }));
  if(m.markers) candle.setMarkers(m.markers);
  hdr(m.meta);
  if(m.signals && m.signals.length) flash(m.signals);
}

/* ───── هدر / لجند / نوتیف ───── */
function hdr(meta){
  const st = document.getElementById('st');
  if(!meta){ st.className = ''; st.textContent = 'live · ' + new Date().toLocaleTimeString(); return; }
  document.getElementById('sym').textContent = meta.symbol || '';
  const fin = meta.final ?? meta.last, finp = meta.final_pct ?? meta.change_pct;
  const lst = meta.last ?? fin, lstp = meta.last_pct ?? meta.change_pct;
  document.getElementById('fin').textContent = fmt(fin);
  const a = document.getElementById('finp'); a.textContent = pct(finp); a.className = (finp || 0) >= 0 ? 'up' : 'dn';
  document.getElementById('lst').textContent = fmt(lst);
  const b = document.getElementById('lstp'); b.textContent = pct(lstp); b.className = (lstp || 0) >= 0 ? 'up' : 'dn';
  document.getElementById('q').textContent = meta.queue ? (meta.queue === 'buy' ? '🟢 صف خرید' : '🔴 صف فروش') : '';
  if(!st.classList.contains('sig')) st.textContent = 'live · ' + (meta.updated || '');
}
function flash(sig){
  const st = document.getElementById('st'); st.className = 'sig';
  st.textContent = '🔔 ' + sig.map(x => x.indicator.split('#')[0] + ' ' + x.signal + ' @' + fmt(x.price)).join(' | ');
  setTimeout(() => hdr(null), 7000);
}
function onCrosshair(p){
  if(!legend) return;
  const base = legend.querySelector('span').textContent;
  if(!p.time || !p.seriesData.get(candle)){ legend.innerHTML = '<span>' + base + '</span>'; return; }
  const c = p.seriesData.get(candle), v = p.seriesData.get(vol);
  const cls = c.close >= c.open ? 'up' : 'dn';
  legend.innerHTML = '<span>' + base + '</span>' +
    `<span class="${cls}">O ${fmt(c.open)} H ${fmt(c.high)} L ${fmt(c.low)} C ${fmt(c.close)}</span>` +
    (v ? `<span>V ${(v.value/1e6).toFixed(2)}M</span>` : '');
}

/* ───── WebSocket ───── */
let ws = null, pingTimer = null;
function connect(){
  ws = new WebSocket(WS_URL);
  ws.onopen = () => { document.getElementById('st').textContent = 'connected'; clearInterval(pingTimer);
    pingTimer = setInterval(() => { if(ws.readyState === 1) ws.send('ping'); }, 20000); };
  ws.onmessage = e => { const m = JSON.parse(e.data); if(m.type === 'init') build(m); else if(m.type === 'update') update(m); };
  ws.onerror = () => {};
  ws.onclose = () => { document.getElementById('st').textContent = 'reconnecting…'; setTimeout(connect, 2000); };
}
connect();
window.addEventListener('resize', () => charts.forEach(c => c.applyOptions({width: W()})));
</script>
</body></html>"""


def chart_html(ws_url: str, height: int = 620) -> str:
    return _TEMPLATE.replace("__WS_URL__", ws_url).replace("__HEIGHT__", str(int(height)))