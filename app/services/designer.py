"""Senior-designer agent: turns a lead (name, sector, city, reviews, their real photos, your notes) into a
complete design brief — palette, typography, copy, sections, offer — that templates/proposal.html renders.

Runs on the Claude API (model in settings.DESIGN_MODEL) with a strict JSON schema so the output is always
renderable. Without ANTHROPIC_API_KEY it falls back to curated sector presets, so the system never blocks.
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Literal, Optional

import re

from pydantic import BaseModel, Field, field_validator

from ..config import settings

FONTS = {"Cairo", "Almarai", "Tajawal", "IBM Plex Sans Arabic", "Noto Kufi Arabic", "Amiri", "Changa", "El Messiri", "Markazi Text", "Readex Pro"}

Kind = Literal["restaurant", "clinic", "beauty", "contractor", "realestate", "education", "auto", "fitness", "retail", "business"]


class Service(BaseModel):
    title: str = Field(max_length=60)
    desc: str = Field(max_length=160)
    price: str = Field(default="", max_length=30)  # e.g. "من 250 ر.س" or ""


class Section(BaseModel):
    id: Literal["services", "gallery", "about", "steps", "reviews", "hours", "faq", "offer"]
    title: str = Field(max_length=60)
    subtitle: str = Field(default="", max_length=140)


class Brief(BaseModel):
    kind: Kind
    brand_name: str = Field(max_length=80)
    tagline: str = Field(max_length=80, description="Short Arabic tagline under the logo")
    headline: str = Field(max_length=90, description="Hero headline, Arabic, benefit-led, max 9 words")
    subheadline: str = Field(max_length=220, description="Hero paragraph, Arabic, 1-2 sentences")
    cta_primary: str = Field(max_length=30)
    cta_secondary: str = Field(max_length=30)
    palette: dict[str, str] = Field(description="Hex colors: primary, accent, dark, light, paper")
    font_display: str = Field(default="Cairo", description="Google Font for headings: Cairo | Almarai | Tajawal | IBM Plex Sans Arabic | Noto Kufi Arabic | Amiri")
    font_body: str = Field(default="IBM Plex Sans Arabic")
    mood: str = Field(max_length=80, description="e.g. فاخر وهادئ / دافئ وعائلي / حديث وجريء")
    hero_photo: int = Field(default=0, description="Index into photos to use as the hero background, -1 for none")
    services: list[Service] = Field(min_length=3, max_length=6)
    sections: list[Section] = Field(min_length=3, max_length=7)
    about: str = Field(max_length=500)
    steps: list[str] = Field(default_factory=list, max_length=4)
    faq: list[dict[str, str]] = Field(default_factory=list, description="[{q,a}] max 4")
    reviews_note: str = Field(default="", max_length=120)
    offer_title: str = Field(default="موقع احترافي كامل بـ 1,000 ر.س شهريًا", max_length=80)
    offer_points: list[str] = Field(default_factory=list, max_length=6)
    design_rationale: str = Field(max_length=400, description="Why this palette/mood fits this business (shown to the salesperson, not the client)")

    @field_validator("palette")
    @classmethod
    def _palette(cls, v: dict[str, str]) -> dict[str, str]:
        out = {}
        for k in ("primary", "accent", "dark", "light", "paper"):
            val = str(v.get(k, "")).strip()
            if k == "paper" and not val:
                val = "#FFFFFF"
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?|#[0-9A-Fa-f]{3}", val):
                raise ValueError(f"palette.{k} must be a hex color")
            out[k] = val
        return out

    @field_validator("font_display", "font_body")
    @classmethod
    def _font(cls, v: str) -> str:
        return v if v in FONTS else "Cairo"

    @field_validator("hero_photo")
    @classmethod
    def _hero(cls, v: int) -> int:
        return max(-1, min(int(v), 20))


SYSTEM = """أنت مدير إبداعي ومصمم جرافيك أول (Senior Art Director) متخصص في هوية العلامات التجارية ومواقع الأعمال الصغيرة في السعودية.
مهمتك: إعداد Design Brief كامل لموقع إلكتروني مخصص لمنشأة واحدة، بحيث يشعر صاحبها فور فتح الصفحة أن هذا "موقعه هو" ويوافق على العرض.

قواعد الجودة:
- اللغة: عربية فصحى بسيطة بنبرة سعودية مهذبة، بدون مبالغة تسويقية رخيصة، بدون إيموجي.
- العنوان الرئيسي يقدّم فائدة للعميل النهائي (مثلاً: "ابتسامتك في أيدٍ أمينة") لا وصفًا للمنشأة.
- الألوان: استخرجها من صور المنشأة الحقيقية إن وُجدت (لون الشعار/الديكور/الطعام)، وإلا من طبيعة النشاط. تباين عالٍ، لون أساسي واحد + لون تمييز واحد فقط. تجنّب الألوان المبتذلة (الأحمر الصارخ للمطاعم، الوردي الفاقع للتجميل).
- الخطوط: عناوين Cairo أو Almarai أو Noto Kufi Arabic للطابع الحديث، Amiri للفخامة التراثية؛ النص IBM Plex Sans Arabic أو Tajawal.
- الخدمات: حقيقية ومناسبة للقطاع والمدينة، أسعار واقعية بالريال إن كان القطاع يعرضها عادة، وإلا اتركها فارغة.
- اختر صورة البطل: أفضل صورة تُظهر المكان/المنتج بوضوح وإضاءة جيدة، وإن كانت كل الصور ضعيفة اختر -1.
- الأقسام: اختر ما يخدم هذا النشاط فقط (مطعم: services=المنيو + gallery + hours؛ عيادة: services + about + steps + faq؛ مقاولات: services + gallery + steps + reviews).
- offer_points: 4-6 نقاط قصيرة لما يشمله اشتراك 1,000 ر.س/شهر (تصميم، نطاق، استضافة، تحديث شهري، زر واتساب، ظهور في قوقل) — ثابتة الجوهر، غيّر الصياغة فقط.
- design_rationale: سطران للبائع يشرحان لماذا اخترت هذا المزاج والألوان، ليستخدمهما في الحديث مع العميل."""

PRESETS: dict[str, dict] = {
    "restaurant": dict(palette={"primary": "#8C3B1A", "accent": "#D9A441", "dark": "#1F1512", "light": "#FBF5EC", "paper": "#FFFFFF"}, font_display="Cairo", font_body="IBM Plex Sans Arabic", mood="دافئ وعائلي",
        headline="طعم يجمع العائلة على طاولة واحدة", subheadline="أطباق تُحضّر يوميًا بمكوّنات طازجة، وحجز وطلب مباشر عبر واتساب دون انتظار.", cta_primary="احجز طاولة", cta_secondary="شاهد المنيو",
        services=[Service(title="الأطباق الرئيسية", desc="مندي، مظبي، كبسة عائلية بحجم يكفي الجميع", price="من 38 ر.س"), Service(title="وجبات العائلة", desc="صواني تكفي 4 إلى 8 أشخاص للعزائم والمناسبات", price="من 140 ر.س"), Service(title="الحلويات والقهوة", desc="كنافة طازجة من الفرن وقهوة عربية بالتمر", price="من 22 ر.س"), Service(title="الطلبات الخارجية", desc="تغليف محكم وتوصيل لكل الأحياء خلال 30 دقيقة", price="")],
        sections=[Section(id="services", title="المنيو", subtitle="أشهر أطباقنا، والقائمة الكاملة تُحدّث شهريًا"), Section(id="gallery", title="من داخل المطعم"), Section(id="hours", title="الموقع وأوقات العمل"), Section(id="reviews", title="آراء الزوار"), Section(id="offer", title="ما الذي ستحصل عليه")],
        about="بدأنا من مطبخ صغير وصرنا وجهة العائلات في الحي. نحافظ على الوصفة الأصلية ونطبخ بمكوّنات طازجة كل يوم.", steps=["اختر من المنيو", "اطلب أو احجز عبر واتساب", "استلم في المطعم أو بالتوصيل"]),
    "clinic": dict(palette={"primary": "#0F5C6E", "accent": "#5FB3C6", "dark": "#0B2830", "light": "#EEF6F8", "paper": "#FFFFFF"}, font_display="Almarai", font_body="IBM Plex Sans Arabic", mood="هادئ وموثوق",
        headline="رعاية تشعر معها بالاطمئنان من أول زيارة", subheadline="فريق طبي مرخّص، مواعيد دقيقة، وحجز مباشر خلال دقيقة عبر واتساب.", cta_primary="احجز موعدًا", cta_secondary="تعرّف على خدماتنا",
        services=[Service(title="الفحص والاستشارة", desc="تقييم شامل وخطة علاج واضحة من أول زيارة", price="من 150 ر.س"), Service(title="العلاجات التخصصية", desc="بأحدث الأجهزة وبإشراف استشاريين", price=""), Service(title="المتابعة", desc="متابعة دورية وتذكير بالمواعيد عبر واتساب", price="")],
        sections=[Section(id="services", title="خدماتنا"), Section(id="steps", title="رحلة المريض"), Section(id="about", title="عن العيادة"), Section(id="faq", title="أسئلة شائعة"), Section(id="offer", title="ما الذي ستحصل عليه")],
        about="عيادة مرخّصة من هيئة التخصصات الصحية، نلتزم بالخصوصية والمواعيد ونشرح كل خطوة قبل البدء.", steps=["احجز موعدك", "تقييم واستشارة", "خطة علاج واضحة", "متابعة مستمرة"],
        faq=[{"q": "هل تقبلون التأمين؟", "a": "نعمل مع عدد من شركات التأمين، تواصل معنا للتأكد من شركتك."}, {"q": "كم مدة الانتظار؟", "a": "المواعيد محجوزة مسبقًا، ولا يتجاوز الانتظار 10 دقائق."}]),
    "beauty": dict(palette={"primary": "#6B4E3D", "accent": "#C9A27E", "dark": "#2A1F1A", "light": "#F7F1EC", "paper": "#FFFFFF"}, font_display="Amiri", font_body="Tajawal", mood="فاخر وهادئ",
        headline="لحظة عناية تستحقينها", subheadline="خدمات تجميل بأيدي متخصصات، بمنتجات أصلية، وحجز فوري عبر واتساب.", cta_primary="احجزي موعدك", cta_secondary="الخدمات والأسعار",
        services=[Service(title="العناية بالبشرة", desc="تنظيف عميق وجلسات نضارة بمنتجات طبية", price="من 250 ر.س"), Service(title="الشعر", desc="قص، صبغ، علاجات بروتين وكيراتين", price="من 120 ر.س"), Service(title="المكياج والمناسبات", desc="مكياج سهرة وعرائس مع تجربة مسبقة", price="من 350 ر.س"), Service(title="الأظافر", desc="مانيكير وباديكير وجل بأحدث الألوان", price="من 80 ر.س")],
        sections=[Section(id="services", title="خدماتنا"), Section(id="gallery", title="من أعمالنا"), Section(id="reviews", title="آراء عميلاتنا"), Section(id="hours", title="الموقع وأوقات العمل"), Section(id="offer", title="ما الذي ستحصلين عليه")],
        about="مساحة نسائية بالكامل، خصوصية تامة، وفريق مدرّب على أحدث التقنيات.", steps=[]),
    "contractor": dict(palette={"primary": "#1F3A5F", "accent": "#E0A33A", "dark": "#0F1C2E", "light": "#EEF2F7", "paper": "#FFFFFF"}, font_display="Cairo", font_body="IBM Plex Sans Arabic", mood="قوي وموثوق",
        headline="ننفّذ مشروعك بدقة وفي الوقت المتفق عليه", subheadline="مقاولات وتشطيبات بضمان مكتوب، عرض سعر واضح خلال 24 ساعة.", cta_primary="اطلب عرض سعر", cta_secondary="شاهد أعمالنا",
        services=[Service(title="البناء والترميم", desc="هيكل، ترميم، وتوسعة بإشراف مهندس", price=""), Service(title="التشطيبات", desc="دهانات، جبس، أرضيات، وأعمال داخلية", price=""), Service(title="الكهرباء والسباكة", desc="تأسيس وصيانة بمواد معتمدة", price=""), Service(title="العوازل", desc="عزل مائي وحراري للأسطح والخزانات بضمان 10 سنوات", price="")],
        sections=[Section(id="services", title="خدماتنا"), Section(id="gallery", title="مشاريع نفّذناها"), Section(id="steps", title="كيف نعمل"), Section(id="reviews", title="آراء العملاء"), Section(id="offer", title="ما الذي ستحصل عليه")],
        about="سجل تجاري وتصنيف معتمد، فريق فني ثابت، ونلتزم بجدول زمني مكتوب لكل مشروع.", steps=["معاينة مجانية", "عرض سعر مفصّل", "تنفيذ بجدول زمني", "تسليم وضمان"]),
    "business": dict(palette={"primary": "#12263A", "accent": "#E0A33A", "dark": "#0B1622", "light": "#F3F5F8", "paper": "#FFFFFF"}, font_display="Cairo", font_body="IBM Plex Sans Arabic", mood="حديث وواثق",
        headline="خدمة تستحق الثقة، وتواصل بضغطة واحدة", subheadline="نخدم عملاءنا بفريق محترف وأسعار واضحة، وعرض سعر خلال دقائق عبر واتساب.", cta_primary="اطلب عرض سعر", cta_secondary="خدماتنا",
        services=[Service(title="الخدمة الأساسية", desc="ما يحصل عليه العميل ولماذا يختارك", price=""), Service(title="خدمة إضافية", desc="السرعة، الجودة، الضمان", price=""), Service(title="باقات", desc="خيارات تناسب الأفراد والشركات", price="")],
        sections=[Section(id="services", title="خدماتنا"), Section(id="about", title="من نحن"), Section(id="steps", title="كيف نعمل"), Section(id="reviews", title="آراء العملاء"), Section(id="offer", title="ما الذي ستحصل عليه")],
        about="منشأة سعودية مرخّصة تخدم عملاءها بجودة والتزام.", steps=["تواصل", "معاينة", "عرض سعر", "تنفيذ وضمان"]),
}
PRESETS["realestate"] = {**PRESETS["business"], "palette": {"primary": "#243B2F", "accent": "#B99457", "dark": "#101B15", "light": "#F1F3EF", "paper": "#FFFFFF"}, "mood": "راقٍ وهادئ", "headline": "عقارك القادم يبدأ من هنا", "cta_primary": "تواصل مع مستشار"}
PRESETS["education"] = {**PRESETS["business"], "palette": {"primary": "#2C4A9B", "accent": "#F2B134", "dark": "#14213D", "light": "#EEF2FA", "paper": "#FFFFFF"}, "mood": "مرح ومنظّم", "headline": "بيئة تعليمية يحبها الأطفال ويطمئن لها الأهل", "cta_primary": "سجّل الآن"}
PRESETS["auto"] = {**PRESETS["contractor"], "palette": {"primary": "#1B1B1B", "accent": "#E63946", "dark": "#0D0D0D", "light": "#F2F2F2", "paper": "#FFFFFF"}, "mood": "قوي وحديث", "headline": "سيارتك بأيدٍ خبيرة، وبسعر واضح قبل البدء", "cta_primary": "احجز موعد صيانة"}
PRESETS["fitness"] = {**PRESETS["business"], "palette": {"primary": "#0E1A2B", "accent": "#7CE577", "dark": "#070D16", "light": "#EEF1F5", "paper": "#FFFFFF"}, "mood": "طاقة وحماس", "headline": "ابدأ اليوم، والنتيجة خلال 30 يومًا", "cta_primary": "جرّب مجانًا"}
PRESETS["retail"] = {**PRESETS["beauty"], "palette": {"primary": "#3B2F2F", "accent": "#B08968", "dark": "#1D1616", "light": "#F8F4F0", "paper": "#FFFFFF"}, "mood": "أنيق", "headline": "تشكيلة مختارة بعناية، تصلك لباب البيت", "cta_primary": "اطلب عبر واتساب"}

SECTOR_TO_KIND = {"مطاعم": "restaurant", "عيادات": "clinic", "تجميل": "beauty", "مقاولات": "contractor", "عقار": "realestate", "تعليم": "education", "سيارات": "auto", "صحة ولياقة": "fitness", "تجزئة": "retail", "منزل وخدمات": "contractor", "قانون ومحاسبة": "business", "مناسبات": "beauty", "حيوانات": "clinic"}

OFFER_POINTS = ["تصميم مخصص بهويتكم وشعاركم وصوركم", "نطاق خاص واستضافة سريعة وشهادة أمان", "ظهور في نتائج قوقل وخرائط قوقل", "زر واتساب واتصال مباشر في كل صفحة", "تحديث المحتوى والأسعار شهريًا", "بدون مبلغ مقدّم، وإلغاء بإشعار شهر"]


def kind_for(sector: str, kind: str = "") -> str:
    if kind in PRESETS:
        return kind
    for k, v in SECTOR_TO_KIND.items():
        if k and k in (sector or ""):
            return v
    return "business"


def preset_brief(lead, kind: str = "") -> Brief:
    k = kind_for(getattr(lead, "sector", ""), kind)
    p = PRESETS[k]
    return Brief(kind=k, brand_name=lead.name, tagline=f"{lead.sector or 'خدمات'} · {lead.city or 'السعودية'}", headline=p["headline"], subheadline=p["subheadline"],
                 cta_primary=p["cta_primary"], cta_secondary=p["cta_secondary"], palette=p["palette"], font_display=p["font_display"], font_body=p["font_body"], mood=p["mood"],
                 hero_photo=0, services=p["services"], sections=p["sections"], about=p["about"], steps=p.get("steps", []), faq=p.get("faq", []),
                 offer_points=OFFER_POINTS, design_rationale=f"قالب {k} الجاهز — لتخصيص حقيقي أضف مفتاح ANTHROPIC_API_KEY وصور المنشأة.")


def _image_block(path: Path) -> Optional[dict]:
    mt = mimetypes.guess_type(str(path))[0] or ""
    if mt not in ("image/jpeg", "image/png", "image/webp", "image/gif") or path.stat().st_size > 4_500_000:
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.standard_b64encode(path.read_bytes()).decode()}}


def api_configured() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


async def generate_brief(lead, photo_paths: list[Path], notes: str = "", kind: str = "", instagram_bio: str = "") -> tuple[Brief, str]:
    """Return (brief, source). source is 'claude' or 'preset'."""
    if not api_configured():
        return preset_brief(lead, kind), "preset"
    import anthropic

    k = kind_for(getattr(lead, "sector", ""), kind)
    content: list[dict] = []
    for i, p in enumerate(photo_paths[:6]):
        blk = _image_block(Path(p))
        if blk:
            content.append({"type": "text", "text": f"صورة رقم {i} من صور المنشأة:"})
            content.append(blk)
    facts = {
        "brand_name": lead.name, "sector": lead.sector, "city": lead.city, "suggested_kind": k,
        "google_rating": float(lead.rating) if getattr(lead, "rating", None) is not None else None, "google_reviews": getattr(lead, "reviews", None),
        "existing_website": getattr(lead, "website", "") or None, "website_issues": getattr(lead, "site_issues", "") or None,
        "instagram": getattr(lead, "instagram", "") or None, "instagram_bio": instagram_bio or None,
        "salesperson_notes": notes or None, "photos_count": len(content) // 2,
        "offer": "موقع احترافي كامل بـ 1,000 ريال شهريًا بدون مبلغ مقدّم، يشمل التصميم والنطاق والاستضافة والتحديث الشهري",
    }
    content.append({"type": "text", "text": "بيانات المنشأة (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1) + "\n\nأعدّ الـ Design Brief الآن. الصور مفهرسة من 0 بترتيب ظهورها أعلاه."})

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = await client.messages.parse(
        model=settings.DESIGN_MODEL,
        max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        output_format=Brief,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return preset_brief(lead, kind), "preset"
    brief: Brief = resp.parsed_output
    if not brief.offer_points:
        brief.offer_points = OFFER_POINTS
    return brief, "claude"


# Alternative palettes offered on the proposal page ("which style do you prefer?") — the client taps and the page re-themes live.
ALT_PALETTES = [
    {"id": "warm", "name": "دافئ", "primary": "#8C3B1A", "accent": "#D9A441", "dark": "#1F1512", "light": "#FBF5EC"},
    {"id": "calm", "name": "هادئ", "primary": "#0F5C6E", "accent": "#5FB3C6", "dark": "#0B2830", "light": "#EEF6F8"},
    {"id": "luxury", "name": "فاخر", "primary": "#2A1F1A", "accent": "#C9A27E", "dark": "#15100D", "light": "#F7F1EC"},
    {"id": "bold", "name": "جريء", "primary": "#12263A", "accent": "#E0A33A", "dark": "#0B1622", "light": "#F3F5F8"},
    {"id": "fresh", "name": "منعش", "primary": "#1E5E3F", "accent": "#7CE577", "dark": "#0E2A1D", "light": "#EEF6F1"},
]
