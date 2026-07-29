export default {
  async scheduled(event, env, ctx) {
    try {
      const res = await fetch(env.RENDER_API + '/api/buscar?q=concurso');
      const data = await res.json();
      const resultados = data.resultados || [];
      const lastJson = await env.KV.get('last_urls');
      const lastUrls = lastJson ? JSON.parse(lastJson) : [];
      const novos = resultados.filter(r => !lastUrls.includes(r.url));
      if (novos.length > 0) {
        const subsJson = await env.KV.get('subscriptions');
        const subscriptions = subsJson ? JSON.parse(subsJson) : [];
        for (const sub of subscriptions) {
          try {
            await fetch(sub.endpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'text/plain', 'TTL': '86400' },
              body: novos.length + ' novos sinais'
            });
          } catch(e) {}
        }
        await env.KV.put('last_urls', JSON.stringify(resultados.map(r => r.url).slice(0, 50)));
      }
    } catch(e) { console.error(e.message); }
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/subscribe' && request.method === 'POST') {
      const sub = await request.json();
      const subsJson = await env.KV.get('subscriptions');
      const subs = subsJson ? JSON.parse(subsJson) : [];
      const filtered = subs.filter(s => s.endpoint !== sub.endpoint);
      filtered.push(sub);
      await env.KV.put('subscriptions', JSON.stringify(filtered));
      return new Response('OK', { headers: { 'Access-Control-Allow-Origin': '*' } });
    }
    return new Response('Sintoniza Worker OK', { headers: { 'Access-Control-Allow-Origin': '*' } });
  }
};
