var subs = [];
var lastUrls = [];

export default {
  async scheduled(event, env, ctx) {
    try {
      var res = await fetch("https://sintoniza-api.onrender.com/api/buscar?q=concurso");
      var data = await res.json();
      var resultados = data.resultados || [];
      var novos = resultados.filter(function(r) { return lastUrls.indexOf(r.url) < 0; });
      if (novos.length > 0 && subs.length > 0) {
        for (var i = 0; i < subs.length; i++) {
          try { await fetch(subs[i].endpoint, { method: "POST", headers: { "Content-Type": "text/plain" }, body: novos.length + " novos sinais" }); } catch(e) {}
        }
      }
      lastUrls = resultados.map(function(r) { return r.url; }).slice(0, 50);
    } catch(e) {}
  },
  async fetch(request, env) {
    var url = new URL(request.url);
    if (url.pathname === "/subscribe" && request.method === "POST") {
      var sub = await request.json();
      subs = subs.filter(function(s) { return s.endpoint !== sub.endpoint; });
      subs.push(sub);
      return new Response("OK", { headers: { "Access-Control-Allow-Origin": "*" } });
    }
    if (url.pathname === "/proxy") {
      var target = url.searchParams.get("url");
      if (!target) return new Response("Missing url", { status: 400, headers: { "Access-Control-Allow-Origin": "*" } });
      try {
        var resp = await fetch(target, { headers: { "User-Agent": "Mozilla/5.0" } });
        var body = await resp.text();
        return new Response(body, { headers: { "Content-Type": "application/xml", "Access-Control-Allow-Origin": "*" } });
      } catch(e) {
        return new Response("Proxy error: " + e.message, { status: 502, headers: { "Access-Control-Allow-Origin": "*" } });
      }
    }
    return new Response("Sintoniza OK", { headers: { "Access-Control-Allow-Origin": "*" } });
  }
};
