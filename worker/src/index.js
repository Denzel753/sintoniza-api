/**
 * Cloudflare Worker — Sintoniza Concursos Push
 * Cron: a cada 30min verifica novos concursos e envia push
 */

export default {
  async scheduled(event, env, ctx) {
    // Fetch from Render API
    try {
      const res = await fetch(`${env.RENDER_API}/api/buscar?q=concurso+publico`);
      const data = await res.json();
      const resultados = data.resultados || [];
      
      // Get last known URLs from KV
      const lastJson = await env.KV.get('last_urls');
      const lastUrls = lastJson ? JSON.parse(lastJson) : [];
      
      // Find new ones
      const novos = resultados.filter(r => !lastUrls.includes(r.url));
      
      if (novos.length > 0) {
        // Get subscriptions from KV
        const subsJson = await env.KV.get('subscriptions');
        const subscriptions = subsJson ? JSON.parse(subsJson) : [];
        
        // Send push to all subscribers
        const payload = JSON.stringify({
          title: '📡 Sintoniza Concursos',
          body: `${novos.length} novos sinais encontrados!`,
          icon: '/assets/favicon.svg',
          data: { url: '/' }
        });
        
        const vapidKeys = {
          publicKey: env.VAPID_PUBLIC_KEY,
          privateKey: env.VAPID_PRIVATE_KEY,
          subject: 'mailto:saraivaejuca@gmail.com'
        };
        
        for (const sub of subscriptions) {
          try {
            await sendPush(sub, payload, vapidKeys);
          } catch(e) {
            // Remove invalid subscriptions
            console.error('Push failed:', e.message);
          }
        }
        
        // Update last URLs
        const allUrls = resultados.map(r => r.url).slice(0, 50);
        await env.KV.put('last_urls', JSON.stringify(allUrls));
      }
    } catch(e) {
      console.error('Worker error:', e.message);
    }
  },
  
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // POST /subscribe — save push subscription
    if (url.pathname === '/subscribe' && request.method === 'POST') {
      const sub = await request.json();
      const subsJson = await env.KV.get('subscriptions');
      const subs = subsJson ? JSON.parse(subsJson) : [];
      // Remove duplicates
      const filtered = subs.filter(s => s.endpoint !== sub.endpoint);
      filtered.push(sub);
      await env.KV.put('subscriptions', JSON.stringify(filtered));
      return new Response('OK', { 
        status: 200,
        headers: { 'Access-Control-Allow-Origin': '*' }
      });
    }
    
    // GET /vapid — return public key
    if (url.pathname === '/vapid') {
      return new Response(env.VAPID_PUBLIC_KEY, {
        headers: { 'Access-Control-Allow-Origin': '*' }
      });
    }
    
    return new Response('Sintoniza Worker', { 
      headers: { 'Access-Control-Allow-Origin': '*' }
    });
  }
};

async function sendPush(subscription, payload, vapidKeys) {
  // Web Push Protocol implementation
  const sub = typeof subscription === 'string' ? JSON.parse(subscription) : subscription;
  
  // Generate VAPID JWT (simplified)
  const encoder = new TextEncoder();
  const header = { typ: 'JWT', alg: 'ES256' };
  const jwtHeader = btoa(JSON.stringify(header));
  const now = Math.floor(Date.now() / 1000);
  const claims = { sub: vapidKeys.subject, exp: now + 86400, aud: new URL(sub.endpoint).origin };
  const jwtPayload = btoa(JSON.stringify(claims));
  
  // Import VAPID key
  const keyData = Uint8Array.from(atob(vapidKeys.privateKey.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey('raw', keyData.slice(0, 32), { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, key, encoder.encode(jwtHeader + '.' + jwtPayload));
  const jwt = jwtHeader + '.' + jwtPayload + '.' + btoa(String.fromCharCode(...new Uint8Array(sig)));
  
  // Encrypt payload
  const encryptedPayload = await encryptPayload(encoder.encode(payload), sub.keys);
  
  const response = await fetch(sub.endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Encoding': 'aes128gcm',
      'Authorization': 'vapid t=' + jwt + ', k=' + vapidKeys.publicKey,
      'TTL': '86400'
    },
    body: encryptedPayload
  });
  
  if (!response.ok) throw new Error('Push failed: ' + response.status);
}

async function encryptPayload(payload, keys) {
  // Simplified — in production use web-push library
  return payload;
}
