"""Service agreement text for the website subscription. Editable in Settings (terms_text / terms_version);
placeholders: {company} {contact} {phone} {sender} {fee} {vat} {total} {start_date} {billing_day} {domain}."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Setting

DEFAULT_VERSION = "1.0"

DEFAULT_TERMS = """اتفاقية اشتراك في خدمة موقع إلكتروني

الطرف الأول (مقدّم الخدمة): {sender}
الطرف الثاني (العميل): {company} — {contact} — جوال {phone}

1. نطاق الخدمة
يقدّم الطرف الأول للطرف الثاني موقعًا إلكترونيًا احترافيًا يشمل: التصميم وفق هوية العميل، النطاق (أو ربط نطاق العميل)، الاستضافة وشهادة الأمان، زر واتساب واتصال، الربط بخرائط قوقل، وتحديث المحتوى (الأسعار، الخدمات، الصور، أوقات العمل) بما لا يتجاوز طلبًا واحدًا أسبوعيًا، يُنفَّذ خلال 24 ساعة عمل.

2. المقابل المالي
رسوم اشتراك شهرية قدرها {fee} ريال سعودي + ضريبة القيمة المضافة 15% ({vat} ريال) = {total} ريال شهريًا، بدون أي مبلغ مقدّم. تصدر الفاتورة في يوم {billing_day} من كل شهر، وتُسدَّد خلال 7 أيام من تاريخها عبر رابط الدفع أو التحويل البنكي.

3. المدة والإلغاء
تبدأ الاتفاقية بتاريخ {start_date} وتتجدد شهريًا تلقائيًا. يحق لأي طرف إنهاؤها بإشعار كتابي (رسالة واتساب كافية) قبل 30 يومًا. عند الإنهاء يتوقف الموقع بنهاية الشهر المدفوع، ويحق للعميل نقل نطاقه إن كان مسجّلًا باسمه.

4. التأخر في السداد
عند تأخر السداد أكثر من 14 يومًا يحق للطرف الأول إيقاف الموقع مؤقتًا حتى السداد، ويُعاد تشغيله خلال 24 ساعة من استلام المبلغ.

5. المحتوى والملكية
المحتوى (الشعار، الصور، النصوص، الأسعار) ملك للعميل ومسؤوليته، ويقرّ بحقه في استخدامه. التصميم والقوالب والشفرة ملك للطرف الأول وتُرخَّص للعميل طوال مدة الاشتراك. يحق للطرف الأول وضع سطر "تصميم واستضافة {sender}" في تذييل الموقع.

6. حدود المسؤولية
يلتزم الطرف الأول ببذل العناية المهنية لإبقاء الموقع متاحًا بنسبة لا تقل عن 99% شهريًا، ولا يتحمل مسؤولية الأضرار غير المباشرة أو فقدان الأرباح أو انقطاع خدمات طرف ثالث (مزودو النطاقات، قوقل، واتساب).

7. حماية البيانات
تُستخدم بيانات العميل وزوّار موقعه لتشغيل الخدمة فقط وفق نظام حماية البيانات الشخصية في المملكة العربية السعودية، ولا تُباع أو تُشارك مع أطراف أخرى.

8. أحكام عامة
تخضع هذه الاتفاقية لأنظمة المملكة العربية السعودية. يُعد قبول الطرف الثاني إلكترونيًا (إدخال الاسم والضغط على «أوافق») توقيعًا ملزمًا وفق نظام التعاملات الإلكترونية، ويُحتفظ بسجل القبول (الاسم، التاريخ والوقت، عنوان الاتصال)."""


def version(db: Session) -> str:
    s = db.get(Setting, "terms_version")
    return s.value if s and s.value else DEFAULT_VERSION


def template(db: Session) -> str:
    s = db.get(Setting, "terms_text")
    return s.value if s and s.value.strip() else DEFAULT_TERMS


def render(db: Session, client) -> str:
    sender = db.get(Setting, "sender_name")
    fee = int(client.monthly_fee or 0)
    vat = round(fee * 0.15)
    return (template(db)
            .replace("{company}", client.company or "")
            .replace("{contact}", client.contact_name or "—")
            .replace("{phone}", f"+{client.phone}" if client.phone else "—")
            .replace("{sender}", (sender.value if sender and sender.value else settings.SENDER_NAME))
            .replace("{fee}", f"{fee:,}").replace("{vat}", f"{vat:,}").replace("{total}", f"{fee + vat:,}")
            .replace("{start_date}", str(client.start_date or ""))
            .replace("{billing_day}", str(client.billing_day or 1))
            .replace("{domain}", client.domain or "—"))
