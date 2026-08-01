/* ===================================================================
   CHARTS — Chart.js wrappers (sparklines + finance charts)
=================================================================== */

const Charts = (() => {
  let monthlyChart, methodChart;
  const sparklines = {};

  function themeColors(){
    const dark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
      grid: dark ? 'rgba(255,255,255,.06)' : 'rgba(15,23,42,.06)',
      text: dark ? '#8592b0' : '#647192',
    };
  }

  function drawSparkline(canvasId, dataPoints, color){
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (sparklines[canvasId]) sparklines[canvasId].destroy();
    sparklines[canvasId] = new Chart(ctx, {
      type: 'line',
      data: { labels: dataPoints.map((_,i)=>i), datasets: [{
        data: dataPoints, borderColor: color, borderWidth: 2, tension: .4,
        pointRadius: 0, fill: true,
        backgroundColor: (context) => {
          const g = context.chart.ctx.createLinearGradient(0,0,0,28);
          g.addColorStop(0, color+'55'); g.addColorStop(1, color+'00');
          return g;
        }
      }]},
      options: {
        responsive:false, animation:{ duration:900, easing:'easeOutCubic' },
        plugins:{ legend:{display:false}, tooltip:{enabled:false} },
        scales:{ x:{display:false}, y:{display:false} },
        elements:{ point:{radius:0} }
      }
    });
  }

  function renderMonthly(sortedMonths, months){
    const { grid, text } = themeColors();
    const ctxM = document.getElementById('monthlyIncomeChart').getContext('2d');
    if (monthlyChart) monthlyChart.destroy();
    monthlyChart = new Chart(ctxM, {
      type:'bar',
      data:{
        labels: sortedMonths,
        datasets:[{
          label:'درآمد (تومان)', data: sortedMonths.map(m=>months[m]/10),
          backgroundColor:'rgba(74,144,226,.55)', borderColor:'#4A90E2', borderWidth:1, borderRadius:10,
          hoverBackgroundColor:'rgba(74,144,226,.85)'
        }]
      },
      options:{
        responsive:true, animation:{ duration:800, easing:'easeOutQuart' },
        plugins:{ legend:{display:false} },
        scales:{
          y:{ grid:{color:grid}, ticks:{ color:text, callback:v=>(v/1000000).toFixed(0)+'M' } },
          x:{ grid:{display:false}, ticks:{ color:text } }
        }
      }
    });
  }

  function renderMethods(labels, values){
    const { text } = themeColors();
    const ctx2 = document.getElementById('methodChart').getContext('2d');
    if (methodChart) methodChart.destroy();
    methodChart = new Chart(ctx2, {
      type:'doughnut',
      data:{ labels, datasets:[{ data: values, backgroundColor:['#22c55e','#3b82f6','#f59e0b','#8b5cf6'], borderWidth:0 }] },
      options:{
        animation:{ duration:800, easing:'easeOutQuart' },
        plugins:{ legend:{ position:'bottom', labels:{ font:{size:10}, color:text } } }
      }
    });
  }

  let simpleBarCharts = {};
  /** Generic single-series bar chart, reused by the student portal's payment-history card. */
  function renderSimpleBar(canvasId, labels, values, color='#4A90E2'){
    const { grid, text } = themeColors();
    const ctx = document.getElementById(canvasId).getContext('2d');
    if (simpleBarCharts[canvasId]) simpleBarCharts[canvasId].destroy();
    simpleBarCharts[canvasId] = new Chart(ctx, {
      type:'bar',
      data:{ labels, datasets:[{ label:'', data: values, backgroundColor: color+'99', borderColor: color, borderWidth:1, borderRadius:8, hoverBackgroundColor: color }] },
      options:{
        responsive:true, animation:{ duration:800, easing:'easeOutQuart' },
        plugins:{ legend:{display:false} },
        scales:{
          y:{ grid:{color:grid}, ticks:{ color:text, callback:v=>(v/1000000)+'M' } },
          x:{ grid:{display:false}, ticks:{ color:text } }
        }
      }
    });
  }

  function refreshThemeColors(){
    // Re-render charts currently on screen so grid/tick colors match the new theme
    if (monthlyChart) monthlyChart.update();
    if (methodChart) methodChart.update();
    Object.values(simpleBarCharts).forEach(c => c.update());
  }

  return { drawSparkline, renderMonthly, renderMethods, renderSimpleBar, refreshThemeColors };
})();
