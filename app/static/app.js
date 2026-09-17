/* Bassir Leads — vanilla JS SPA. State in memory + token in sessionStorage. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const app = $("#app");
  const S = { token: sessionStorage.getItem("token") || "", user: null, view: "dash", facets: { cities: [], sectors: [], statuses: [] }, templates: [], settings: {}, filters: { q: "", status: "", city: "", sector: "", due: false, page: 1 }, leads: { items: [], total: 0 } };
  const STATUS_AR = { new: "جديد", contacted: "تم التواصل", replied: "رد", demo_sent: "أُرسل النموذج", negotiating: "تفاوض", won: "تم التعاقد", lost: "خسارة", do_not_contact: "لا تتواصل" };
  const STAGE_AR = { first: "رسالة أولى", follow_up: "متابعة", objection: "رد على اعتراض", closing: "إغلاق" };
  const CSTAT_AR = { onboarding: "تجهيز", active: "نشط", paused: "موقوف", cancelled: "ملغي" };
  const INV_AR = { unpaid: "غير مدفوعة", paid: "مدفوعة", overdue: "متأخرة", void: "ملغاة" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");

  function toast(msg, err = false) {
    const t = $("#toast"); t.innerHTML = `<div class="${err ? "err" : ""}">${esc(msg)}</div>`;
    requestAnimationFrame(() => t.firstChild.classList.add("show"));
    setTimeout(() => t.firstChild && t.firstChild.classList.remove("show"), 2600);
  }

  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (S.token) headers.Authorization = "Bearer " + S.token;
    if (opts.body && !(opts.body instanceof FormData)) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.body); }
    const r = await fetch(path, { ...opts, headers });
    if (r.status === 401) { logout(); throw new Error("انتهت الجلسة، سجّل الدخول من جديد"); }
    if (r.status === 204) return null;
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
    return data;
  }

  function logout() { S.token = ""; S.user = null; sessionStorage.removeItem("token"); render(); }

  // ---------- LOGIN ----------
  function renderLogin() {
    app.innerHTML = `<div class="login"><div class="card">
      <h1>Bassir <span>Leads</span></h1><p>نظام إدارة العملاء المحتملين والاشتراكات</p>
      <label>البريد الإلكتروني</label><input id="em" type="email" autocomplete="username" dir="ltr">
      <label>كلمة المرور</label><input id="pw" type="password" autocomplete="current-password" dir="ltr">
      <div class="actions"><button class="btn btn-dark btn-block" id="go">تسجيل الدخول</button></div>
    </div></div>`;
    const go = async () => {
      try { const d = await api("/api/auth/login", { method: "POST", body: { email: $("#em").value.trim(), password: $("#pw").value } });
        S.token = d.access_token; S.user = d.user; sessionStorage.setItem("token", S.token); await boot();
      } catch (e) { toast(e.message, true); }
    };
    $("#go").onclick = go; $("#pw").onkeydown = (e) => e.key === "Enter" && go();
  }

  // ---------- SHELL ----------
  const TABS = [["dash", "🏠", "الرئيسية"], ["leads", "👥", "العملاء"], ["clients", "💼", "الاشتراكات"], ["templates", "💬", "الرسائل"], ["settings", "⚙️", "الإعدادات"]];
  function shell(inner) {
    app.innerHTML = `<div class="shell">
      <div class="top"><div class="brand">Bassir <span>Leads</span></div><div class="who">${esc(S.user.name)} · <a href="#" id="lo" style="text-decoration:underline">خروج</a></div></div>
      <nav class="tabs">${TABS.map(([v, i, l]) => `<a href="#${v}" class="${S.view === v ? "active" : ""}"><i>${i}</i>${l}</a>`).join("")}</nav>
      <div class="main">${inner}</div></div>`;
    $("#lo").onclick = (e) => { e.preventDefault(); logout(); };
  }

  // ---------- DASHBOARD ----------
  async function renderDash() {
    shell(`<div class="empty">جارٍ التحميل…</div>`);
    const d = await api("/api/dashboard");
    const max = Math.max(1, ...d.series.map((x) => x.sent));
    const funnel = ["new", "contacted", "replied", "demo_sent", "negotiating", "won", "lost"];
    shell(`
      <div class="kpis">
        <div class="kpi accent"><b>${fmt(d.mrr)} ر.س</b><span>الدخل الشهري المتكرر (MRR)</span></div>
        <div class="kpi"><b>${d.clients_active}</b><span>اشتراك نشط</span></div>
        <div class="kpi"><b>${d.sent_today} / ${d.daily_cap}</b><span>رسائل اليوم</span></div>
        <div class="kpi"><b>${d.follow_ups_due}</b><span>متابعات مستحقة</span></div>
        <div class="kpi"><b>${d.leads_total}</b><span>إجمالي العملاء المحتملين</span></div>
        <div class="kpi"><b>${d.reply_rate}%</b><span>نسبة الرد</span></div>
        <div class="kpi"><b>${d.win_rate}%</b><span>نسبة الإغلاق</span></div>
        <div class="kpi"><b>${fmt(d.unpaid_total)} ر.س</b><span>فواتير غير مدفوعة (${d.invoices_overdue} متأخرة)</span></div>
      </div>
      <div class="row row-2">
        <div class="card"><h2>الرسائل — آخر 14 يوم <span class="hint">${d.sent_week} هذا الأسبوع</span></h2>
          <div class="spark">${d.series.map((x) => `<div style="height:${Math.round((x.sent / max) * 100)}%" title="${x.day}: ${x.sent}"><span>${x.sent || ""}</span></div>`).join("")}</div>
          <div class="hint" style="display:flex;justify-content:space-between;margin-top:4px"><span>${d.series[0].day}</span><span>اليوم</span></div></div>
        <div class="card"><h2>قمع المبيعات</h2>
          ${funnel.map((s) => `<div style="margin:6px 0"><div style="display:flex;justify-content:space-between;font-size:.85rem"><span>${STATUS_AR[s]}</span><b>${d.by_status[s]}</b></div><div class="bar"><i style="width:${Math.round((d.by_status[s] / Math.max(1, d.leads_total)) * 100)}%"></i></div></div>`).join("")}
        </div>
      </div>
      <div class="actions"><a class="btn btn-dark" href="#leads?due=1">افتح المتابعات المستحقة</a><a class="btn btn-ghost" href="#leads?status=new">ابدأ الإرسال للجدد</a></div>`);
  }

  // ---------- LEADS ----------
  async function loadLeads() {
    const f = S.filters; const p = new URLSearchParams({ page: f.page, size: 50 });
    if (f.q) p.set("q", f.q); if (f.status) p.set("status", f.status); if (f.city) p.set("city", f.city); if (f.sector) p.set("sector", f.sector); if (f.due) p.set("due", "true");
    S.leads = await api("/api/leads?" + p);
  }
  async function renderLeads() {
    shell(`<div class="empty">جارٍ التحميل…</div>`);
    [S.facets] = await Promise.all([api("/api/leads/facets"), loadLeads()]);
    const f = S.filters; const today = new Date().toISOString().slice(0, 10);
    const opt = (arr, cur, map) => `<option value="">الكل</option>` + arr.map((v) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(map ? map[v] : v)}</option>`).join("");
    shell(`
      <div class="card">
        <div class="row row-4">
          <input id="fq" placeholder="بحث بالاسم أو الجوال" value="${esc(f.q)}">
          <select id="fs">${opt(S.facets.statuses, f.status, STATUS_AR)}</select>
          <select id="fc">${opt(S.facets.cities, f.city)}</select>
          <select id="fsec">${opt(S.facets.sectors, f.sector)}</select>
        </div>
        <div class="actions">
          <button class="btn ${f.due ? "btn-dark" : "btn-ghost"} btn-sm" id="fdue">المستحقة اليوم</button>
          <button class="btn btn-ghost btn-sm" id="add">+ عميل</button>
          <button class="btn btn-ghost btn-sm" id="imp">استيراد CSV</button>
          <button class="btn btn-ghost btn-sm" id="disc">بحث Google Maps</button>
          <a class="btn btn-ghost btn-sm" id="exp" href="#">تصدير</a>
          <span class="hint" style="align-self:center">${S.leads.total} نتيجة</span>
        </div>
        <input type="file" id="file" accept=".csv" hidden>
      </div>
      <div class="card" id="list">${S.leads.items.length ? S.leads.items.map(leadRow(today)).join("") : `<div class="empty">لا يوجد عملاء — أضف يدويًا أو استورد CSV</div>`}</div>
      ${S.leads.total > 50 ? `<div class="actions"><button class="btn btn-ghost btn-sm" id="prev" ${f.page === 1 ? "disabled" : ""}>السابق</button><span class="hint">صفحة ${f.page}</span><button class="btn btn-ghost btn-sm" id="next" ${f.page * 50 >= S.leads.total ? "disabled" : ""}>التالي</button></div>` : ""}`);
    const refilter = () => { f.q = $("#fq").value; f.status = $("#fs").value; f.city = $("#fc").value; f.sector = $("#fsec").value; f.page = 1; renderLeads(); };
    $("#fq").onchange = refilter; $("#fs").onchange = refilter; $("#fc").onchange = refilter; $("#fsec").onchange = refilter;
    $("#fdue").onclick = () => { f.due = !f.due; f.page = 1; renderLeads(); };
    $("#add").onclick = () => leadForm();
    $("#imp").onclick = () => $("#file").click();
    $("#disc").onclick = () => discoverForm();
    $("#file").onchange = async (e) => { const fd = new FormData(); fd.append("file", e.target.files[0]); try { const r = await api("/api/leads/import", { method: "POST", body: fd }); toast(`أُضيف ${r.added} — مكرر ${r.skipped_duplicates} — غير صالح ${r.skipped_invalid}`); renderLeads(); } catch (err) { toast(err.message, true); } };
    $("#exp").onclick = async (e) => { e.preventDefault(); const r = await fetch("/api/leads/export", { headers: { Authorization: "Bearer " + S.token } }); const b = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "leads.csv"; a.click(); };
    const pv = $("#prev"), nx = $("#next"); if (pv) pv.onclick = () => { f.page--; renderLeads(); }; if (nx) nx.onclick = () => { f.page++; renderLeads(); };
    $("#list").querySelectorAll(".lead").forEach((el) => el.onclick = () => openLead(+el.dataset.id));
  }
  const demoFor = (l) => { const base = (S.settings.demo_url || "").trim(); if (!base) return ""; const q = new URLSearchParams(); if (l.name) q.set("n", l.name); if (l.city) q.set("c", l.city); if (l.phone) q.set("p", l.phone); if (l.sector) q.set("s", l.sector); return base + (base.includes("?") ? "&" : "?") + q.toString(); };
  const leadRow = (today) => (l) => `<div class="lead ${l.priority === 1 ? "pri1" : ""}" data-id="${l.id}">
      <div><div class="n">${esc(l.name)}</div><div class="m">${esc(l.city)}${l.sector ? " · " + esc(l.sector) : ""}${l.rating ? " · ★" + l.rating : ""}${l.website ? (l.site_score != null ? ` · <span class="tag ${l.site_score < 60 ? "lost" : "won"}">موقع ${l.site_score}</span>` : " · 🌐 لديه موقع") : " · بدون موقع"}</div></div>
      <div style="text-align:left"><span class="tag ${l.status}">${STATUS_AR[l.status]}</span>${l.next_follow_up && l.next_follow_up <= today && !["won", "lost", "do_not_contact"].includes(l.status) ? ' <span class="tag due">متابعة</span>' : ""}<div class="p">+${l.phone}</div></div></div>`;

  function drawer(html) {
    const bg = document.createElement("div"); bg.className = "drawer-bg"; bg.innerHTML = `<div class="drawer">${html}<button class="close" aria-label="إغلاق">×</button></div>`;
    document.body.appendChild(bg);
    const close = () => bg.remove();
    bg.onclick = (e) => e.target === bg && close();
    $(".close", bg).onclick = close;
    return { el: bg, close };
  }

  function leadForm(lead) {
    const d = drawer(`<h3>${lead ? "تعديل عميل" : "عميل جديد"}</h3>
      <label>اسم المنشأة</label><input id="n" value="${esc(lead?.name || "")}">
      ${lead ? "" : `<label>الجوال</label><input id="p" dir="ltr" placeholder="05xxxxxxxx">`}
      <div class="row row-2"><div><label>المدينة</label><input id="c" list="cities" value="${esc(lead?.city || "")}"><datalist id="cities">${S.facets.cities.map((c) => `<option value="${esc(c)}">`).join("")}</datalist></div>
      <div><label>النشاط</label><input id="s" list="sectors" value="${esc(lead?.sector || "")}"><datalist id="sectors">${S.facets.sectors.map((c) => `<option value="${esc(c)}">`).join("")}</datalist></div></div>
      <label>إنستقرام</label><input id="ig" dir="ltr" value="${esc(lead?.instagram || "")}">
      <label>الأولوية</label><select id="pr"><option value="1" ${lead?.priority === 1 ? "selected" : ""}>عالية</option><option value="2" ${!lead || lead.priority === 2 ? "selected" : ""}>عادية</option><option value="3" ${lead?.priority === 3 ? "selected" : ""}>منخفضة</option></select>
      <label>ملاحظات</label><textarea id="no">${esc(lead?.notes || "")}</textarea>
      <div class="actions"><button class="btn btn-dark" id="sv">حفظ</button></div>`);
    $("#sv", d.el).onclick = async () => {
      const body = { name: $("#n", d.el).value.trim(), city: $("#c", d.el).value.trim(), sector: $("#s", d.el).value.trim(), instagram: $("#ig", d.el).value.trim(), priority: +$("#pr", d.el).value, notes: $("#no", d.el).value };
      try {
        if (lead) await api(`/api/leads/${lead.id}`, { method: "PATCH", body });
        else await api("/api/leads", { method: "POST", body: { ...body, phone: $("#p", d.el).value } });
        toast("تم الحفظ"); d.close(); renderLeads();
      } catch (e) { toast(e.message, true); }
    };
  }

  async function openLead(id) {
    const [lead, acts] = await Promise.all([api(`/api/leads/${id}`), api(`/api/leads/${id}/activities`)]);
    try { lead._proposal_url = (await api(`/api/leads/${id}/proposal`)).url; } catch (e) { lead._proposal_url = ""; }
    const tpls = S.templates.filter((t) => t.is_active);
    const d = drawer(`<h3>${esc(lead.name)}</h3><div class="hint ltr" style="text-align:right">+${lead.phone} ${lead.city ? " · " + esc(lead.city) : ""} ${lead.sector ? " · " + esc(lead.sector) : ""}</div>
      <div class="actions">
        <a class="btn btn-ghost btn-sm" href="tel:+${lead.phone}">📞 اتصال</a>
        ${lead.instagram ? `<a class="btn btn-ghost btn-sm" target="_blank" rel="noopener" href="${esc(/^https?:/.test(lead.instagram) ? lead.instagram : "https://instagram.com/" + lead.instagram.replace("@", ""))}">إنستقرام</a>` : ""}
        ${lead.maps_url ? `<a class="btn btn-ghost btn-sm" target="_blank" rel="noopener" href="${esc(lead.maps_url)}">الخريطة</a>` : ""}
        ${lead.website ? `<a class="btn btn-ghost btn-sm" target="_blank" rel="noopener" href="${esc(/^https?:/.test(lead.website) ? lead.website : "https://" + lead.website)}">الموقع${lead.site_score != null ? " " + lead.site_score + "/100" : ""}</a><button class="btn btn-ghost btn-sm" id="aud">🔍 فحص الموقع</button>` : ""}
        <a class="btn btn-ghost btn-sm" target="_blank" rel="noopener" href="${esc(demoFor(lead))}">👁 النموذج باسمهم</a>
        <button class="btn btn-dark btn-sm" id="prop">🎨 عرض مصمم</button>
        <button class="btn btn-ghost btn-sm" id="ed">تعديل</button>
        ${lead.status !== "won" ? `<button class="btn btn-ghost btn-sm" id="conv">✔ تحويل لعميل</button>` : ""}
        ${S.user.role === "admin" ? `<button class="btn btn-danger btn-sm" id="del">حذف</button>` : ""}
      </div>
      <div class="card" style="margin-top:14px"><h2>الحالة والمتابعة</h2>
        <div class="row row-2"><div><label>الحالة</label><select id="st">${S.facets.statuses.map((s) => `<option value="${s}" ${s === lead.status ? "selected" : ""}>${STATUS_AR[s]}</option>`).join("")}</select></div>
        <div><label>المتابعة القادمة</label><input id="fu" type="date" value="${lead.next_follow_up || ""}"></div></div>
        <div class="actions"><button class="btn btn-dark btn-sm" id="svst">حفظ</button></div></div>
      <div class="card"><h2>إرسال واتساب</h2>
        <label>القالب</label><select id="tp">${tpls.map((t) => `<option value="${t.id}" ${t.sector && t.sector === lead.sector ? "selected" : ""}>${esc(STAGE_AR[t.stage])} — ${esc(t.name)}</option>`).join("")}</select>
        <label>أو نص مخصص (يتجاوز القالب)</label><textarea id="custom" style="min-height:70px" placeholder="اتركه فارغًا لاستخدام القالب"></textarea>
        <label>معاينة</label><div class="preview" id="pv"></div>
        <label>متابعة بعد (أيام)</label><input id="fd" type="number" min="0" max="60" value="2">
        <div class="actions"><button class="btn btn-wa btn-block" id="send">فتح واتساب وتسجيل الإرسال</button></div>
        <p class="hint" style="margin-top:6px">${S.settings.whatsapp_api ? "الإرسال عبر WhatsApp Cloud API مفعّل." : "يفتح واتساب برسالة جاهزة — اضغط إرسال داخل واتساب."}</p></div>
      <div class="card"><h2>ملاحظة / مكالمة</h2><div class="row row-2"><select id="ak"><option value="note">ملاحظة</option><option value="call">مكالمة</option></select><input id="ac" placeholder="ماذا حدث؟"></div><div class="actions"><button class="btn btn-ghost btn-sm" id="adda">إضافة</button></div></div>
      <div class="card"><h2>السجل</h2>${acts.length ? acts.map((a) => `<div class="act"><small>${new Date(a.created_at + "Z").toLocaleString("ar-SA")} · ${{ whatsapp: "واتساب", call: "مكالمة", note: "ملاحظة", status: "تغيير حالة", email: "بريد" }[a.kind] || a.kind}${a.channel ? " (" + a.channel + ")" : ""}</small><pre>${esc(a.content)}</pre></div>`).join("") : `<div class="hint">لا يوجد نشاط بعد</div>`}</div>`);
    const issues = (lead.site_issues || "").split("\n").filter(Boolean).map((x) => "• " + x).join("\n");
    const render = (body) => body.replaceAll("{name}", lead.name).replaceAll("{city}", lead.city).replaceAll("{sector}", lead.sector).replaceAll("{activity}", lead.sector).replaceAll("{website}", lead.website || "").replaceAll("{issues}", issues).replaceAll("{demo}", lead._proposal_url || demoFor(lead) || "[الرابط]").replaceAll("{proposal}", lead._proposal_url || "[رابط العرض]").replaceAll("{sender}", S.settings.sender_name || "");
    const pv = () => { const c = $("#custom", d.el).value.trim(); const t = tpls.find((x) => x.id === +$("#tp", d.el).value); $("#pv", d.el).textContent = render(c || (t ? t.body : "")); };
    pv(); $("#tp", d.el).onchange = pv; $("#custom", d.el).oninput = pv;
    $("#send", d.el).onclick = async () => {
      const custom = $("#custom", d.el).value.trim();
      const win = window.open("", "_blank");  // open synchronously to avoid popup blockers on mobile
      try {
        const r = await api(`/api/leads/${id}/send`, { method: "POST", body: { template_id: +$("#tp", d.el).value || null, body: custom || null, follow_up_in_days: +$("#fd", d.el).value } });
        if (r.channel === "wa_api") { win && win.close(); toast(`أُرسلت عبر API (${r.sent_today}/${r.daily_cap})`); }
        else { if (win) win.location = r.wa_link; else window.location = r.wa_link; toast(`سُجّل الإرسال (${r.sent_today}/${r.daily_cap})`); }
        d.close(); renderLeads();
      } catch (e) { win && win.close(); toast(e.message, true); }
    };
    $("#svst", d.el).onclick = async () => { try { await api(`/api/leads/${id}`, { method: "PATCH", body: { status: $("#st", d.el).value, next_follow_up: $("#fu", d.el).value || null } }); toast("تم الحفظ"); d.close(); renderLeads(); } catch (e) { toast(e.message, true); } };
    $("#adda", d.el).onclick = async () => { try { await api(`/api/leads/${id}/activities`, { method: "POST", body: { kind: $("#ak", d.el).value, content: $("#ac", d.el).value } }); d.close(); openLead(id); } catch (e) { toast(e.message, true); } };
    $("#ed", d.el).onclick = () => { d.close(); leadForm(lead); };
    $("#prop", d.el).onclick = () => { d.close(); proposalForm(lead); };
    const aud = $("#aud", d.el); if (aud) aud.onclick = async () => { aud.disabled = true; aud.textContent = "جارٍ الفحص…"; try { const r = await api(`/api/leads/${id}/audit`, { method: "POST" }); toast(`نتيجة الموقع ${r.score}/100 — ${r.issues.length} ملاحظة`); d.close(); openLead(id); } catch (e) { toast(e.message, true); aud.disabled = false; aud.textContent = "🔍 فحص الموقع"; } };
    const conv = $("#conv", d.el); if (conv) conv.onclick = () => { d.close(); clientForm({ lead_id: lead.id, company: lead.name, phone: lead.phone }); };
    const del = $("#del", d.el); if (del) del.onclick = async () => { if (!confirm("حذف العميل نهائيًا؟")) return; await api(`/api/leads/${id}`, { method: "DELETE" }); d.close(); renderLeads(); };
  }

  // ---------- DESIGNED PROPOSAL ----------
  const KIND_AR = { "": "تلقائي حسب النشاط", restaurant: "مطعم / كافيه", clinic: "عيادة", beauty: "تجميل / صالون", contractor: "مقاولات / خدمات منزلية", realestate: "عقار", education: "تعليم", auto: "سيارات", fitness: "لياقة", retail: "تجزئة", business: "منشأة عامة" };
  const TIMING_AR = { this_week: "هذا الأسبوع", this_month: "خلال شهر", thinking: "يفكر", not_interested: "غير مهتم" };
  async function proposalForm(lead) {
    let prop = null; try { prop = await api(`/api/leads/${lead.id}/proposal`); } catch (e) { /* none yet */ }
    const photos = (await api(`/api/leads/${lead.id}/photos`)).photos;
    const d = drawer(`<h3>🎨 عرض مصمم لـ ${esc(lead.name)}</h3>
      <p class="hint">${S.settings.designer_api ? "المصمم الذكي مفعّل: يحلل صور المنشأة ويكتب المحتوى ويختار الألوان." : "<b style='color:var(--warn)'>ANTHROPIC_API_KEY غير مضبوط</b> — سيُستخدم قالب القطاع الجاهز (أضف المفتاح في .env لتصميم مخصص)."}</p>
      ${prop ? `<div class="card" style="background:#F3F8F4"><h2>الرابط الحالي</h2><input dir="ltr" readonly value="${esc(prop.url)}" onclick="this.select()"><div class="actions"><a class="btn btn-ghost btn-sm" target="_blank" rel="noopener" href="${esc(prop.url)}">فتح</a><button class="btn btn-ghost btn-sm" id="cp">نسخ الرابط</button><a class="btn btn-wa btn-sm" target="_blank" rel="noopener" href="https://wa.me/${lead.phone}?text=${encodeURIComponent("هذا عرض تصميم أعددته خصيصًا لـ " + lead.name + ":\n" + prop.url + "\nأخبرني برأيك 🙏")}">إرسال بواتساب</a></div>
        <div class="hint">المصدر: ${esc(prop.source)} · المشاهدات: <b>${prop.views}</b>${prop.last_viewed_at ? " · آخر فتح " + new Date(prop.last_viewed_at + "Z").toLocaleString("ar-SA") : ""}</div>
        ${prop.answered_at ? `<div class="preview" style="margin-top:8px">🎯 <b>أجاب العميل:</b> النمط: ${esc(prop.answers.style || "-")} · الأهم: ${esc((prop.answers.priorities || []).join("، ") || "-")} · التوقيت: ${esc(TIMING_AR[prop.answers.timing] || prop.answers.timing || "-")}${prop.answers.wants_start ? " · <b>✅ ضغط أبغى أبدأ</b>" : ""}${prop.answers.notes ? "\nملاحظاته: " + esc(prop.answers.notes) : ""}</div>` : `<div class="hint">لم يجب العميل على الأسئلة بعد.</div>`}
        <div class="hint" style="margin-top:6px">💡 ${esc(prop.brief.design_rationale || "")}</div></div>` : ""}
      <div class="card"><h2>1) صور المنشأة (${photos.length})</h2>
        <div id="ph" style="display:flex;gap:6px;flex-wrap:wrap">${photos.map((u) => `<img src="${esc(u)}" style="width:72px;height:72px;object-fit:cover;border-radius:8px">`).join("") || '<span class="hint">لا توجد صور — أضف صورهم أو شعارهم، أو اجلبها من قوقل</span>'}</div>
        <div class="actions"><label class="btn btn-ghost btn-sm" style="cursor:pointer">📤 رفع صور<input id="up" type="file" accept="image/*" multiple hidden></label><button class="btn btn-ghost btn-sm" id="gp" ${S.settings.places_api ? "" : "disabled"}>📍 جلب صورهم من قوقل</button></div></div>
      <div class="card"><h2>2) توجيه المصمم</h2>
        <label>نوع القالب</label><select id="kind">${Object.entries(KIND_AR).map(([k, v]) => `<option value="${k}" ${prop && prop.kind === k ? "selected" : ""}>${v}</option>`).join("")}</select>
        <label>ملاحظاتك (ماذا لاحظت في إنستقرامهم/موقعهم؟ ألوان الشعار؟ خدماتهم المميزة؟)</label><textarea id="notes" placeholder="مثال: شعارهم أخضر غامق، متخصصون في تقويم الأسنان، عندهم عرض للطلاب"></textarea>
        <label>نبذة حسابهم في إنستقرام (اختياري)</label><textarea id="bio" style="min-height:60px"></textarea>
        <div class="actions"><button class="btn btn-dark btn-block" id="gen">${prop ? "🔄 إعادة التصميم" : "✨ تصميم العرض الآن"}</button></div></div>`);
    const cp = $("#cp", d.el); if (cp) cp.onclick = () => { navigator.clipboard.writeText(prop.url); toast("نُسخ الرابط"); };
    $("#up", d.el).onchange = async (e) => { const fd = new FormData(); [...e.target.files].forEach((f) => fd.append("files", f)); try { await api(`/api/leads/${lead.id}/photos`, { method: "POST", body: fd }); toast("رُفعت الصور"); d.close(); proposalForm(lead); } catch (err) { toast(err.message, true); } };
    $("#gp", d.el).onclick = async () => { $("#gp", d.el).disabled = true; try { const r = await api(`/api/leads/${lead.id}/photos/google`, { method: "POST" }); toast(`جُلبت ${r.saved.length} صورة`); d.close(); proposalForm(lead); } catch (err) { toast(err.message, true); $("#gp", d.el).disabled = false; } };
    $("#gen", d.el).onclick = async () => { const b = $("#gen", d.el); b.disabled = true; b.textContent = "المصمم يعمل… (قد يستغرق دقيقة)"; try { const r = await api(`/api/leads/${lead.id}/proposal`, { method: "POST", body: { kind: $("#kind", d.el).value, notes: $("#notes", d.el).value, instagram_bio: $("#bio", d.el).value } }); toast(`جاهز (${r.source})`); d.close(); proposalForm(lead); } catch (err) { toast(err.message, true); b.disabled = false; b.textContent = "✨ تصميم العرض الآن"; } };
  }

  function discoverForm() {
    const d = drawer(`<h3>بحث Google Maps</h3><p class="hint">يجلب المنشآت التي <b>ليس لديها موقع إلكتروني</b> ولديها رقم جوال. ${S.settings.places_api ? "" : "<b style='color:var(--bad)'>مفتاح Google Places غير مضبوط في .env</b>"}</p>
      <div class="row row-2"><div><label>النشاط</label><input id="q" placeholder="مطاعم / عيادة أسنان / مقاولات"></div><div><label>المدينة أو الحي</label><input id="c" placeholder="حي حطين الرياض"></div></div>
      <label>الحد الأقصى</label><input id="m" type="number" value="20" min="1" max="60">
      <div class="actions"><button class="btn btn-dark" id="run" ${S.settings.places_api ? "" : "disabled"}>بحث</button><button class="btn btn-wa" id="save" disabled>حفظ الكل كعملاء</button></div><div id="res"></div>`);
    let items = [];
    $("#run", d.el).onclick = async () => {
      $("#res", d.el).innerHTML = `<div class="empty">جارٍ البحث…</div>`;
      try { items = await api("/api/discover", { method: "POST", body: { query: $("#q", d.el).value, city: $("#c", d.el).value, max_results: +$("#m", d.el).value, save: false } });
        $("#res", d.el).innerHTML = items.length ? `<table><tr><th>المنشأة</th><th>الجوال</th><th>★</th><th></th></tr>${items.map((i) => `<tr><td>${esc(i.name)}</td><td class="ltr">+${i.phone}</td><td>${i.rating ?? "-"} (${i.reviews ?? 0})</td><td>${i.already_exists ? '<span class="tag contacted">موجود</span>' : '<span class="tag new">جديد</span>'}</td></tr>`).join("")}</table>` : `<div class="empty">لا نتائج</div>`;
        $("#save", d.el).disabled = !items.some((i) => !i.already_exists);
      } catch (e) { $("#res", d.el).innerHTML = ""; toast(e.message, true); }
    };
    $("#save", d.el).onclick = async () => { try { const r = await api("/api/discover", { method: "POST", body: { query: $("#q", d.el).value, city: $("#c", d.el).value, max_results: +$("#m", d.el).value, save: true } }); toast(`حُفظ ${r.filter((i) => !i.already_exists).length} عميل`); d.close(); renderLeads(); } catch (e) { toast(e.message, true); } };
  }

  // ---------- CLIENTS ----------
  async function renderClients() {
    shell(`<div class="empty">جارٍ التحميل…</div>`);
    const cs = await api("/api/clients");
    shell(`<div class="card"><div class="actions" style="margin:0"><button class="btn btn-dark btn-sm" id="add">+ اشتراك</button>${S.user.role === "admin" ? `<button class="btn btn-ghost btn-sm" id="bill">إصدار فواتير هذا الشهر</button>` : ""}<span class="hint" style="align-self:center">${cs.length} عميل</span></div></div>
      ${cs.length ? cs.map((c) => `<div class="card" data-id="${c.id}"><h2>${esc(c.company)} <span class="tag ${c.status}">${CSTAT_AR[c.status]}</span></h2>
        <div class="hint">${esc(c.contact_name)} · <span class="ltr">+${c.phone}</span> · ${fmt(c.monthly_fee)} ر.س/شهر · منذ ${c.start_date}${c.site_url ? ` · <a target="_blank" rel="noopener" href="${esc(c.site_url)}" style="text-decoration:underline">${esc(c.domain || c.site_url)}</a>` : ""}</div>
        ${c.invoices.length ? `<table style="margin-top:8px"><tr><th>الفاتورة</th><th>الفترة</th><th>المبلغ + ض</th><th>الاستحقاق</th><th>الحالة</th><th></th></tr>${c.invoices.sort((a, b) => b.period.localeCompare(a.period)).map((i) => `<tr><td class="ltr">${i.number}</td><td>${i.period}</td><td>${fmt(i.amount + i.vat)}</td><td>${i.due_date}</td><td><span class="tag ${i.status}">${INV_AR[i.status]}</span></td><td>${["unpaid", "overdue"].includes(i.status) ? `<button class="btn btn-ghost btn-sm pay" data-i="${i.id}">تم الدفع</button>` : ""}</td></tr>`).join("")}</table>` : ""}
        <div class="actions"><button class="btn btn-ghost btn-sm edit">تعديل</button></div></div>`).join("") : `<div class="card empty">لا يوجد اشتراكات بعد — حوّل أول عميل من صفحة العملاء</div>`}`);
    $("#add").onclick = () => clientForm();
    const bill = $("#bill"); if (bill) bill.onclick = async () => { try { const r = await api("/api/clients/run-billing", { method: "POST" }); toast(`أُصدرت ${r.length} فاتورة`); renderClients(); } catch (e) { toast(e.message, true); } };
    document.querySelectorAll(".pay").forEach((b) => b.onclick = async () => { try { await api(`/api/clients/invoices/${b.dataset.i}/pay`, { method: "POST" }); toast("سُجّل الدفع"); renderClients(); } catch (e) { toast(e.message, true); } });
    document.querySelectorAll(".edit").forEach((b) => b.onclick = () => clientForm(cs.find((c) => c.id === +b.closest(".card").dataset.id)));
  }
  function clientForm(c) {
    const isNew = !c || !c.id;
    const d = drawer(`<h3>${isNew ? "اشتراك جديد" : "تعديل اشتراك"}</h3>
      <label>الشركة</label><input id="co" value="${esc(c?.company || "")}">
      <div class="row row-2"><div><label>اسم المسؤول</label><input id="cn" value="${esc(c?.contact_name || "")}"></div><div><label>الجوال</label><input id="ph" dir="ltr" value="${esc(c?.phone || "")}" ${isNew ? "" : "disabled"}></div></div>
      <label>البريد</label><input id="em" dir="ltr" value="${esc(c?.email || "")}">
      <div class="row row-2"><div><label>النطاق</label><input id="dm" dir="ltr" value="${esc(c?.domain || "")}"></div><div><label>رابط الموقع</label><input id="su" dir="ltr" value="${esc(c?.site_url || "")}"></div></div>
      <div class="row row-3"><div><label>الرسوم الشهرية</label><input id="fee" type="number" value="${c?.monthly_fee ?? (S.settings.default_price || 1000)}"></div><div><label>يوم الفوترة</label><input id="bd" type="number" min="1" max="28" value="${c?.billing_day ?? 1}"></div><div><label>الحالة</label><select id="cs">${Object.keys(CSTAT_AR).map((k) => `<option value="${k}" ${(c?.status || "onboarding") === k ? "selected" : ""}>${CSTAT_AR[k]}</option>`).join("")}</select></div></div>
      ${isNew ? `<label>تاريخ البداية</label><input id="sd" type="date" value="${new Date().toISOString().slice(0, 10)}">` : ""}
      <label>ملاحظات</label><textarea id="no">${esc(c?.notes || "")}</textarea>
      <div class="actions"><button class="btn btn-dark" id="sv">حفظ</button></div>`);
    $("#sv", d.el).onclick = async () => {
      const body = { company: $("#co", d.el).value.trim(), contact_name: $("#cn", d.el).value.trim(), email: $("#em", d.el).value.trim(), domain: $("#dm", d.el).value.trim(), site_url: $("#su", d.el).value.trim(), monthly_fee: +$("#fee", d.el).value, billing_day: +$("#bd", d.el).value, status: $("#cs", d.el).value, notes: $("#no", d.el).value };
      try {
        if (isNew) await api("/api/clients", { method: "POST", body: { ...body, phone: $("#ph", d.el).value, lead_id: c?.lead_id || null, start_date: $("#sd", d.el).value } });
        else await api(`/api/clients/${c.id}`, { method: "PATCH", body });
        toast("تم الحفظ"); d.close(); location.hash = "#clients"; renderClients();
      } catch (e) { toast(e.message, true); }
    };
  }

  // ---------- TEMPLATES ----------
  async function renderTemplates() {
    S.templates = await api("/api/templates");
    const admin = S.user.role === "admin";
    shell(`<div class="card"><div class="actions" style="margin:0">${admin ? `<button class="btn btn-dark btn-sm" id="add">+ قالب</button>` : ""}<span class="hint" style="align-self:center">المتغيرات: {name} {city} {activity} {demo} {sender}</span></div></div>
      ${S.templates.map((t) => `<div class="card" data-id="${t.id}"><h2>${esc(t.name)} <span><span class="tag new">${STAGE_AR[t.stage]}</span>${t.sector ? ` <span class="tag contacted">${esc(t.sector)}</span>` : ""}${t.is_active ? "" : ' <span class="tag lost">موقوف</span>'}</span></h2><div class="preview" style="max-height:140px">${esc(t.body)}</div>${admin ? `<div class="actions"><button class="btn btn-ghost btn-sm edit">تعديل</button><button class="btn btn-danger btn-sm del">حذف</button></div>` : ""}</div>`).join("")}`);
    if (!admin) return;
    $("#add").onclick = () => tplForm();
    document.querySelectorAll(".edit").forEach((b) => b.onclick = () => tplForm(S.templates.find((t) => t.id === +b.closest(".card").dataset.id)));
    document.querySelectorAll(".del").forEach((b) => b.onclick = async () => { if (!confirm("حذف القالب؟")) return; await api(`/api/templates/${b.closest(".card").dataset.id}`, { method: "DELETE" }); renderTemplates(); });
  }
  function tplForm(t) {
    const d = drawer(`<h3>${t ? "تعديل قالب" : "قالب جديد"}</h3><label>الاسم</label><input id="n" value="${esc(t?.name || "")}">
      <div class="row row-2"><div><label>المرحلة</label><select id="st">${Object.keys(STAGE_AR).map((k) => `<option value="${k}" ${t?.stage === k ? "selected" : ""}>${STAGE_AR[k]}</option>`).join("")}</select></div><div><label>النشاط (اختياري)</label><input id="sec" value="${esc(t?.sector || "")}"></div></div>
      <label>النص</label><textarea id="b" style="min-height:220px">${esc(t?.body || "")}</textarea>
      <label><input type="checkbox" id="act" ${!t || t.is_active ? "checked" : ""} style="width:auto"> مفعّل</label>
      <div class="actions"><button class="btn btn-dark" id="sv">حفظ</button></div>`);
    $("#sv", d.el).onclick = async () => { const body = { name: $("#n", d.el).value, stage: $("#st", d.el).value, sector: $("#sec", d.el).value.trim(), body: $("#b", d.el).value, is_active: $("#act", d.el).checked }; try { if (t) await api(`/api/templates/${t.id}`, { method: "PUT", body }); else await api("/api/templates", { method: "POST", body }); toast("تم الحفظ"); d.close(); renderTemplates(); } catch (e) { toast(e.message, true); } };
  }

  // ---------- SETTINGS ----------
  async function renderSettings() {
    S.settings = await api("/api/settings");
    const admin = S.user.role === "admin";
    const users = admin ? await api("/api/auth/users") : [];
    shell(`<div class="card"><h2>إعدادات الحملة</h2>
        <label>اسم المرسل (يظهر في {sender})</label><input id="sn" value="${esc(S.settings.sender_name)}" ${admin ? "" : "disabled"}>
        <label>رقم واتساب المبيعات (يظهر في صفحة العرض ليتواصل العميل معك) — 9665xxxxxxxx</label><input id="sp" dir="ltr" value="${esc(S.settings.sender_phone || "")}" ${admin ? "" : "disabled"}>
        <label>رابط الموقع النموذجي ({demo}) — يُستبدل تلقائيًا برابط العرض المصمم إن وُجد</label><input id="du" dir="ltr" value="${esc(S.settings.demo_url)}" ${admin ? "" : "disabled"}>
        <div class="row row-2"><div><label>الحد اليومي للرسائل</label><input id="cap" type="number" value="${esc(S.settings.daily_send_cap)}" ${admin ? "" : "disabled"}></div><div><label>السعر الافتراضي (ر.س/شهر)</label><input id="pr" type="number" value="${esc(S.settings.default_price)}" ${admin ? "" : "disabled"}></div></div>
        <p class="hint" style="margin-top:8px">WhatsApp Cloud API: ${S.settings.whatsapp_api ? "مفعّل ✔" : "غير مفعّل (يُستخدم wa.me)"} · Google Places: ${S.settings.places_api ? "مفعّل ✔" : "غير مفعّل"} — تُضبط من ملف .env</p>
        ${admin ? `<div class="actions"><button class="btn btn-dark" id="sv">حفظ</button></div>` : ""}</div>
      <div class="card"><h2>كلمة المرور</h2><label>الحالية</label><input id="cp" type="password" dir="ltr"><label>الجديدة (8+ أحرف)</label><input id="np" type="password" dir="ltr"><div class="actions"><button class="btn btn-ghost" id="chp">تغيير</button></div></div>
      ${admin ? `<div class="card"><h2>المستخدمون</h2><table><tr><th>الاسم</th><th>البريد</th><th>الدور</th><th>الحالة</th><th></th></tr>${users.map((u) => `<tr><td>${esc(u.name)}</td><td class="ltr">${esc(u.email)}</td><td>${u.role === "admin" ? "مدير" : "مندوب"}</td><td><span class="tag ${u.is_active ? "active" : "lost"}">${u.is_active ? "نشط" : "موقوف"}</span></td><td>${u.id !== S.user.id ? `<button class="btn btn-ghost btn-sm tog" data-i="${u.id}">${u.is_active ? "إيقاف" : "تفعيل"}</button>` : ""}</td></tr>`).join("")}</table>
        <div class="row row-4" style="margin-top:12px"><input id="un" placeholder="الاسم"><input id="ue" placeholder="البريد" dir="ltr"><input id="up" placeholder="كلمة المرور" type="password" dir="ltr"><select id="ur"><option value="agent">مندوب</option><option value="admin">مدير</option></select></div>
        <div class="actions"><button class="btn btn-ghost btn-sm" id="addu">+ مستخدم</button></div></div>` : ""}`);
    if (admin) {
      $("#sv").onclick = async () => { try { S.settings = await api("/api/settings", { method: "PUT", body: { sender_name: $("#sn").value, sender_phone: $("#sp").value.replace(/\D/g, ""), demo_url: $("#du").value, daily_send_cap: $("#cap").value, default_price: $("#pr").value } }); toast("تم الحفظ"); } catch (e) { toast(e.message, true); } };
      $("#addu").onclick = async () => { try { await api("/api/auth/users", { method: "POST", body: { name: $("#un").value, email: $("#ue").value, password: $("#up").value, role: $("#ur").value } }); toast("أُضيف المستخدم"); renderSettings(); } catch (e) { toast(e.message, true); } };
      document.querySelectorAll(".tog").forEach((b) => b.onclick = async () => { await api(`/api/auth/users/${b.dataset.i}/toggle`, { method: "PATCH" }); renderSettings(); });
    }
    $("#chp").onclick = async () => { try { await api("/api/auth/change-password", { method: "POST", body: { current_password: $("#cp").value, new_password: $("#np").value } }); toast("تم تغيير كلمة المرور"); $("#cp").value = $("#np").value = ""; } catch (e) { toast(e.message, true); } };
  }

  // ---------- ROUTER ----------
  const VIEWS = { dash: renderDash, leads: renderLeads, clients: renderClients, templates: renderTemplates, settings: renderSettings };
  async function render() {
    if (!S.token) return renderLogin();
    const [view, qs] = (location.hash.slice(1) || "dash").split("?");
    if (qs) { const p = new URLSearchParams(qs); S.filters = { ...S.filters, status: p.get("status") || "", due: p.get("due") === "1", page: 1 }; history.replaceState(null, "", "#" + view); }
    S.view = VIEWS[view] ? view : "dash";
    try { await VIEWS[S.view](); } catch (e) { if (S.token) { shell(`<div class="card empty">${esc(e.message)}</div>`); } }
  }
  async function boot() {
    try { S.user = await api("/api/auth/me"); [S.templates, S.settings] = await Promise.all([api("/api/templates"), api("/api/settings")]); render(); }
    catch (e) { logout(); }
  }
  window.addEventListener("hashchange", render);
  if (S.token) boot(); else render();
})();
