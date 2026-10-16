from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
import secrets

from .models import User, Template, Invoice, Client

TEMPLATES = [
    ("رسالة أولى — عامة", "first", "", """السلام عليكم، معك {sender}.

شفت حساب {name} على الإنستقرام/سناب وواضح إن الشغل ممتاز 👌
لكن لاحظت إنه ما فيه موقع إلكتروني — يعني أي عميل يبحث في قوقل عن "{activity} في {city}" ما يلقاكم، ويروح للمنافس اللي عنده موقع.

سويت لكم نموذج مبدئي عشان تشوفون الفكرة:
{demo}

الخدمة: موقع احترافي كامل (تصميم + استضافة + نطاق + صيانة وتحديث شهري) بـ 1,000 ريال شهريًا، بدون أي مبلغ مقدّم.

تحبون أجهّز لكم نسخة باسمكم وشعاركم؟ تأخذ يومين فقط."""),
    ("رسالة أولى — مطاعم وكافيهات", "first", "مطاعم", """السلام عليكم، معك {sender}.

{name} — حسابكم في الإنستقرام شكله يفتح النفس 😄
بس سؤال: لما أحد يبحث في قوقل "{activity} قريب مني" في {city}، تطلعون؟ بدون موقع إلكتروني الجواب غالبًا لا، والمنيو والحجز يضيعون بين الستوريات.

هذا نموذج لموقع مطعم سويناه (منيو + حجز واتساب + موقع على الخريطة):
{demo}

نجهّز لكم موقع كامل باسمكم بـ 1,000 ريال/شهر شامل كل شيء، وبدون دفعة أولى.
أرسل لكم نسخة تجريبية باسم {name}؟"""),
    ("رسالة أولى — عيادات ومراكز تجميل", "first", "عيادات", """السلام عليكم، معك {sender}.

{name} — تابعت حسابكم وشغلكم مرتب ماشاءالله.
المشكلة إن المريض اللي يبحث في قوقل عن "{activity} في {city}" يلقى المنافسين اللي عندهم موقع، وما يلقاكم — والحجز عندكم كله عبر الدايركت.

نموذج موقع عيادة (الخدمات + الأطباء + حجز موعد مباشر):
{demo}

موقع كامل باسمكم بـ 1,000 ريال شهريًا شامل الاستضافة والصيانة، بدون مبلغ مقدّم.
أجهّز لكم نسخة تجريبية باسم العيادة؟"""),
    ("رسالة أولى — مقاولين وعقار", "first", "مقاولات", """السلام عليكم، معك {sender}.

{name} — شفت أعمالكم على الحساب وواضح الخبرة.
لكن الجهات والعملاء الكبار أول شيء يسوونه قبل التعاقد: يبحثون عن الشركة في قوقل. بدون موقع إلكتروني، الثقة تنقص والفرصة تروح لغيركم.

نموذج موقع لشركة {activity} (سابقة الأعمال + الخدمات + نموذج طلب عرض سعر):
{demo}

موقع احترافي كامل بـ 1,000 ريال/شهر شامل النطاق والاستضافة والتحديث، بدون دفعة مقدمة.
تحبون أرسل لكم نسخة تجريبية باسم الشركة؟"""),
    ("رسالة أولى — موقعهم ضعيف", "first", "", """السلام عليكم، معك {sender}.

{name} — دخلت على موقعكم {website} وحبيت أنبّهكم بكل صراحة:
{issues}

يعني العميل اللي يوصل لكم من قوقل غالبًا يطلع بدون ما يتواصل، ويروح للمنافس.

سويت لكم نموذج لموقع جديد بنفس نشاطكم عشان تشوفون الفرق:
{demo}

الخدمة: موقع احترافي كامل (تصميم جديد + استضافة + نطاق + صيانة وتحديث شهري) بـ 1,000 ريال شهريًا، بدون أي مبلغ مقدّم، وننقل محتواكم الحالي مجانًا.

تحبون أجهّز لكم نسخة باسمكم؟ تأخذ يومين فقط.
(إذا ما تبون رسائل مني، اكتبوا "إيقاف" وما راح أزعجكم)"""),
    ("First message — English (no website)", "first", "", """Hello, this is {sender}.

I came across {name} on Instagram — great work 👌
One thing I noticed: there is no website. When a customer searches Google for "{activity} in {city}", they can't find you and go to the competitor who has one.

I built a quick sample so you can see the idea:
{demo}

The service: a complete professional website (design + hosting + domain + monthly updates) for SAR 1,000/month, no upfront payment.

Would you like a version with your name and logo? It takes 2 days.
(Reply STOP if you'd rather not hear from me.)"""),
    ("First message — English (weak website)", "first", "", """Hello, this is {sender}.

{name} — I visited your website {website} and, honestly, a few things are costing you customers:
{issues}

Here is a sample of what a new site for your business could look like:
{demo}

Complete redesign + hosting + domain + monthly maintenance for SAR 1,000/month, no upfront payment, and we migrate your current content for free.

Shall I prepare a version with your name? (Reply STOP to opt out.)"""),
    ("تقرير شهري للعميل (بعد النشر)", "closing", "", """مرحبًا {name}، معك {sender} 🙏
تقرير موقعكم {site} لهذا الشهر:
{stats}

يعني عملاء جدد وصلوا لكم من قوقل مباشرة. حدّثنا المنيو/الخدمات مجانًا كالعادة — أرسلوا أي تعديل أو صور من هنا:
{update_link}"""),
    ("تذكير فاتورة الاشتراك", "closing", "", """مرحبًا {name}، معك {sender} 🙏
فاتورة اشتراك الموقع لهذا الشهر جاهزة:
{invoice}

الدفع بمدى أو أبل باي أو تحويل بنكي من نفس الرابط خلال دقيقة. شكرًا لثقتكم 🌹"""),
    ("رد: إيقاف / لا أريد", "objection", "", """تمام، شكرًا لوقتكم 🙏 ما راح أرسل لكم مرة ثانية. بالتوفيق لـ {name}."""),
    ("متابعة (بعد 2–3 أيام)", "follow_up", "", """مرحبًا، {sender} مرة ثانية 🙏
أرسلت لكم قبل يومين نموذج الموقع الخاص بـ {name}:
{demo}

لو الوقت مو مناسب الحين ما فيه مشكلة أبدًا — بس أحب أعرف: تبون أحتفظ بالنموذج لكم أو أوقفه؟"""),
    ("رد: السعر غالي", "objection", "", """فاهمك تمامًا 👍
خلني أوضح: الـ 1,000 شامل التصميم + النطاق + الاستضافة + الأمان + تحديث المحتوى كل شهر — يعني ما فيه أي مصاريف ثانية ولا فني تحتاجونه.
وللمقارنة: موقع من شركة تصميم يكلف 8–15 ألف مقدّم + صيانة سنوية، وبدون تحديثات.
عميل واحد إضافي في الشهر يجيكم من قوقل يغطي الاشتراك. نجرّب شهر واحد؟"""),
    ("رد: عندنا إنستقرام يكفي", "objection", "", """الإنستقرام ممتاز للي يعرفكم أصلًا 👌
لكن العميل الجديد اللي يبحث عن "{activity} في {city}" يبحث في قوقل، مو في إنستقرام — وقوقل ما يعرض حسابات إنستقرام في النتائج الأولى.
الموقع يجيب العميل الجديد، والإنستقرام يخليه يرجع. الاثنين مع بعض.
النموذج جاهز على {demo} — نجرّب؟"""),
    ("إغلاق — بعد الموافقة", "closing", "", """ممتاز! 🎉 عشان نبدأ أحتاج منكم:
1) الشعار + 5–10 صور
2) قائمة الخدمات/المنيو والأسعار
3) رقم الواتساب وموقعكم على الخريطة وأوقات العمل
4) اسم النطاق المفضّل (.com أو .sa)

أرسل لكم العقد والفاتورة الأولى الآن، والموقع يكون جاهز خلال 48 ساعة من استلام المواد."""),
]


def seed(db: Session) -> None:
    for inv in db.query(Invoice).filter(Invoice.token == ""):  # invoices created before payment links existed
        inv.token = secrets.token_urlsafe(18)
    for c in db.query(Client).filter(Client.update_token == ""):
        c.update_token = secrets.token_urlsafe(18)
    if not db.query(User).first():
        db.add(User(email=settings.ADMIN_EMAIL.lower(), name=settings.ADMIN_NAME, password_hash=hash_password(settings.ADMIN_PASSWORD), role="admin"))
    if not db.query(Template).first():
        for name, stage, sector, body in TEMPLATES:
            db.add(Template(name=name, stage=stage, sector=sector, body=body))
    db.commit()
