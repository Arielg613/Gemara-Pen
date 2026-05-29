"""
Gemara Pen — THE BRAIN (offline dictionary engine).

This module is fully self-contained and has NO network dependency. Given a
single Aramaic/Hebrew word, it returns Jastrow dictionary definitions plus a
detected language tag (Hebrew / Aramaic / both).

It is the part that runs ON the pen. To port it to the device you need only:
  1. This file (jastrow.py)
  2. The bundled dictionary data (data/jastrow.json)

Public API:
  analyze(word)  -> dict   full structured result (recommended for the pen)
  lookup(word)   -> list   just the matching entries (convenience)
  detect_language(entry) -> "hebrew" | "aramaic" | "both" | "unknown"
  strip_nikud(text) -> str  remove vowel points / cantillation

How a word is resolved (in order):
  1. exact   — the word is a headword as typed
  2. root    — strip Aramaic/Hebrew prefixes & suffixes to find the root
  3. prefix  — partial match (user typed the start of a root)
"""

import json
import os
import re

_index:          dict | None = None
_tractate_sense: dict | None = None   # {word: {tractate: entry_index}}
_abbreviations:  dict | None = None   # {letters: {full, en}}
_phrases:        dict | None = None   # {phrase: meaning}
_cache: dict = {}   # (normalized_word, tractate) → analyze() result

_DATA_PATH    = os.path.join(os.path.dirname(__file__), "data", "jastrow.json")
_TSENSE_PATH  = os.path.join(os.path.dirname(__file__), "data", "tractate_sense.json")
_ABBREV_PATH  = os.path.join(os.path.dirname(__file__), "data", "abbreviations.json")
_PHRASES_PATH = os.path.join(os.path.dirname(__file__), "data", "phrases.json")

# Aramaic/Hebrew prefixes and suffixes to strip when looking for a root.
# Order matters — longer ones are tried first to avoid partial stripping.
_PREFIXES = [
    # Ithpeal/Ithpaal reflexive-passive binyan prefix (longer first)
    "אית", "את",
    # Hitpael-style (Hebrew borrowed patterns)
    "מת", "הת", "נת",
    # Single-letter prepositions, articles, conjunctions
    "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
    # Single-letter imperfect person-markers and Afel alef
    "א", "י", "נ", "ת",
    # Aramaic present-tense marker קא and specific imperfect prefix תי
    "ק", "תי",
]
_SUFFIXES = [
    # 5-letter (longest first)
    "ייתא",  # Aramaic f. emphatic determinate (קמייתא → קמ)
    # 4-letter
    "תון", "תין", "נון", "נין",
    # 3-letter possessive/plural
    "יות", "יין", "יהם", "יהן", "יכם", "יכן",
    "הון", "הין", "כון", "כין",
    "תם", "תן",
    # 2-letter construct + possessive combos (e.g. שחיטתו → שחיט)
    "תו", "תה", "תך",
    # 2-letter verb / noun endings
    "יה", "יו", "יך", "יי",
    "הם", "הן", "כם", "כן",
    "נא", "נו", "תי",
    "ות", "ין", "ון", "ית",
    "תא", "את",
    "ים",
    "יא",   # Aramaic definite/emphatic plural (מלכיא "the kings")
    "נן",   # Aramaic 1st pl. perfect (חזינן → חזי)
    # 1-letter (last resort — most likely to overshoot)
    "א", "ה", "ת", "ן", "י", "ו", "ך",
]

# Matches Jastrow cross-reference definitions like ", v. רָקַק" or "v. רוֹק, רֵיק."
_XREF_RE = re.compile(r'^,?\s*v\.\s+([א-תְ-ׇ\s,\.]+)', re.UNICODE)

# Non-final → final letter map. After suffix stripping the terminal letter
# of a stem must be in final form to match dictionary headwords.
_TO_FINAL = {"מ": "ם", "נ": "ן", "פ": "ף", "כ": "ך", "צ": "ץ"}

# Prefixes allowed for SECOND-LEVEL stripping (applied after a first-level
# strip already yielded a candidate).  Suffix-stripped candidates have higher
# priority than prefix-only candidates in _resolve, so false positives from
# aggressive second-level stripping are naturally suppressed: the correct
# suffix-stripped root is always tried first.
_SAFE_PREFIXES = {
    "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
    "א", "י", "נ", "ת", "ק",
    "אית", "את", "מת", "הת", "נת",
}


# ── Quick-gloss overrides ────────────────────────────────────────────────────
# Jastrow (1903) was written before modern study of Babylonian Talmudic Aramaic.
# For the ~60 most common Talmudic discourse words it either has the wrong sense,
# no entry at all, or a definition buried in irrelevant detail.
# These one-line glosses take precedence over anything extracted from Jastrow.
# Keys are unvoweled (nikud-stripped).
_QUICK_GLOSSES: dict[str, str] = {
    # ── Discourse / logic particles ──────────────────────────────────────────
    "מאי":        "what?",
    "מאן":        "who?",
    "מני":        "who? — who is the tanna/author of this teaching?",
    "מנו":        "who is he? who is it?",
    "מנא":        "from where? how do we know?",
    "היכי":       "how?",
    "היכא":       "where?",
    "הכי":        "so; thus; in this way",
    "הכא":        "here",
    "התם":        "there",
    "מנלן":       "from where do we derive this?",
    "מדאורייתא":  "by Torah law",
    "מדרבנן":     "by rabbinic law",
    "פשיטא":      "obviously; it is clear",
    "תיקו":       "unresolved (left standing)",
    "קשיא":       "difficulty; objection",
    "קשה":        "difficulty; it is hard",
    "ניחא":       "fine; acceptable; easy",
    "אדרבה":      "on the contrary",
    "אדרבא":      "on the contrary",
    "סייעתא":     "support; corroboration",
    "תיובתא":     "refutation",
    "תיובתיה":    "it refutes him",
    "מיבעיא":     "the question is whether...",
    "בעיא":       "question; unresolved inquiry",
    "איבעיא":     "a question was raised",
    "בעי":        "he asked; he inquired; he sought",
    "הוה אמינא":  "I would have thought",
    "קא משמע לן": "this teaches us",
    "קמשמע לן":   "this teaches us",
    "לאו":        "no; not (emphatic)",
    "אין":        "yes",
    "אלא":        "rather; but; except",
    "דאמר":       "who said; as he said",
    "כלומר":      "that is to say; meaning",
    "היינו":      "that is; that is the same as",
    "הא":         "but; behold; this (particle)",
    "הני":        "these",
    "הנך":        "those",
    "בהדי":       "together with; along with",
    "כגון":       "for example; such as",
    "כיצד":       "how? in what manner?",
    "כיון":       "since; because; once",
    "כיון ד":     "since; because",
    "אע״ג":       "even though; although",
    "אף על גב":   "even though; although",
    "מכל מקום":   "in any case; nevertheless",
    "ממה נפשך":   "either way; from any perspective",
    "בשלמא":      "it is well; granted (introduces a settled point)",
    "בשלמה":      "it is well; granted",
    "אלא מעתה":   "but if so; therefore",
    "דלמא":       "perhaps; maybe",
    "שמא":        "perhaps; lest",
    "ולא":        "and not; but not",
    "ואי":        "and if",
    "ואם":        "and if",
    "כי":         "when; because; that; if",
    "כד":         "when (Aramaic)",
    "עד":         "witness; until; as far as",
    "עד כאן":     "until here; up to this point",
    "מדוע":       "why?",
    # ── Existence ────────────────────────────────────────────────────────────
    "איכא":       "there is; there are",
    "ליכא":       "there is not; there are not",
    "איתא":       "it exists; it is so; there is",
    "ליתא":       "it does not exist; it is not so",
    "כמה":        "how much; how many",
    "הוה":        "was; existed; it was (Aramaic past)",
    "הוי":        "is; be; it is (Aramaic)",
    "הוו":        "they were; there were",
    "הויא":       "it was; it is (f.)",
    "לא הוי":     "it is not; it does not apply",
    # ── Core Talmudic legal terms ─────────────────────────────────────────────
    "מותר":       "permitted; allowed — or: remainder, leftover",
    "אסור":       "forbidden; prohibited",
    "חייב":       "liable; obligated; guilty",
    "פטור":       "exempt; not liable; freed",
    "כשר":        "valid; fit; ritually permitted",
    "פסול":       "invalid; disqualified",
    "טמא":        "ritually impure",
    "טהור":       "ritually pure; clean",
    "נדה":        "menstrual impurity; a woman in niddah",
    "מלאכה":      "work; labor; forbidden Sabbath activity",
    "מצוה":       "commandment; mitzvah; good deed",
    "עבירה":      "transgression; sin",
    "תשובה":      "repentance; answer; response",
    "קנין":       "acquisition; legal act of taking possession",
    "שטר":        "legal document; contract; bill",
    "עדות":       "testimony; evidence; witness statement",
    "שבועה":      "oath; vow",
    "נדר":        "vow; oath",
    "איסור":      "prohibition; something forbidden",
    "היתר":       "permit; something permitted; grounds for permitting",
    "ספק":        "doubt; uncertainty",
    "וודאי":      "certainly; definitely",
    "חזקה":       "presumption; established status; possession",
    "מיגו":       "since (legal principle: credibility from stronger claim)",
    "קל וחומר":   "a fortiori argument (if X then certainly Y)",
    "גזירה שוה":  "verbal analogy (same word used in two laws → they share rules)",
    "ברירה":      "retroactive clarification of ownership or status",
    "פרוזבול":    "legal document transferring loans to court (Hillel's enactment)",
    "הפקר":       "ownerless property; renunciation of ownership",
    "מציאה":      "found object; lost property",
    "גזל":        "theft; robbery; stolen property",
    "גנב":        "to steal; thief",
    "נזק":        "damage; tort",
    "שומר":       "guardian; watchman; custodian",
    "שכירות":     "rental; wages; hire",
    "שאלה":       "borrowing; question; query",
    "פיקדון":     "deposit; object left in trust",
    # ── Common nouns ─────────────────────────────────────────────────────────
    "רבי":        "rabbi; my teacher; Torah sage",
    "בית":        "house; home; the Temple",
    "דין":        "law; judgment; legal case",
    "מעה":        "intestine; bowel",
    "מעים":       "intestines; bowels",
    "מעי":        "intestines; bowels (construct form)",
    "עיר":        "city; town",
    "שוק":        "market; public area; thigh",
    "יד":         "hand; handle; power",
    "רגל":        "foot; leg; festival (pilgrimage)",
    "ראש":        "head; beginning; leader",
    "לב":         "heart; mind",
    "עין":        "eye; spring of water",
    "פה":         "mouth; opening",
    "אב":         "father; source; primary category",
    "אם":         "mother; if",
    "בן":         "son; member of",
    "בת":         "daughter; member of (f.); bath (liquid measure)",
    "אח":         "brother",
    "אחות":       "sister",
    "איש":        "man; person; husband",
    "אשה":        "woman; wife",
    "ארץ":        "land; earth; country",
    "מים":        "water",
    "אש":         "fire",
    "דם":         "blood",
    "כסף":        "silver; money",
    "זהב":        "gold",
    "שדה":        "field",
    "כלי":        "vessel; utensil; tool",
    "בגד":        "garment; cloth",
    "לחם":        "bread; food",
    "בשר":        "meat; flesh",
    "חלב":        "milk; fat",
    "יין":        "wine",
    "שמן":        "oil",
    "מלח":        "salt",
    "זמן":        "time; appointed time",
    "מקום":       "place; location; God (Makom)",
    "דבר":        "thing; word; matter",
    "שם":         "name; there",
    "כן":         "so; yes; thus",
    "לא":         "no; not",
    "כל":         "all; every; any",
    "כלל":        "general rule; principle",
    "פרט":        "specific case; particular",
    "חלק":        "portion; share; part",
    "גבול":       "boundary; border; limit",
    "עולם":       "world; forever; always",
    "חיים":       "life; living",
    "מות":        "death",
    "שלום":       "peace; welfare; wellbeing",
    "אמת":        "truth",
    "שקר":        "falsehood; lie",
    "יום":        "day",
    "לילה":       "night",
    "שנה":        "year",
    "חדש":        "month; new",
    "שעה":        "hour; moment; time",
    "עת":         "time; moment",
    "פעם":        "time; once",
    "תמיד":       "always; the daily offering (Tamid)",
    "כבר":        "already",
    "עוד":        "still; again; more",
    "עתה":        "now",
    "אז":         "then; at that time",
    # ── Key Aramaic nouns ────────────────────────────────────────────────────
    "טעמא":       "reason; rationale",
    "סלקא":       "it arises; it would seem",
    "הלכתא":      "the law; the ruling",
    "כהנא":       "the priest",
    "דינא":       "law; judgment; case",
    "מלכא":       "the king",
    "מלכתא":      "the queen",
    "ממון":       "money; property; monetary matters",
    "ממונא":      "money; property",
    "פלגא":       "half",
    "גופא":       "the main point; the body itself",
    "מילתא":      "a matter; a word; a thing",
    "שמעתא":      "a teaching; a tradition",
    "סוגיא":      "Talmudic discussion; passage",
    "תקנתא":      "rabbinic enactment",
    "איתתא":      "woman",
    "גברא":       "man; person",
    "ינוקא":      "child; infant",
    "ריש":        "head; beginning; chief",
    "גט":         "bill of divorce",
    "שבת":        "Sabbath; to rest",
    "שבתא":       "the Sabbath (Aramaic)",
    "שוקא":       "the market; the public domain",
    "ביתא":       "the house (Aramaic)",
    "ארעא":       "land; ground; earth (Aramaic)",
    "עלמא":       "the world; everyone (Aramaic)",
    "תרי":        "two (Aramaic)",
    "תלת":        "three (Aramaic)",
    "חד":         "one; a certain (Aramaic)",
    "חדא":        "one (f.); once (Aramaic)",
    "כולהו":      "all of them",
    "כולה":       "all of it",
    "כולי":       "all; entire",
    "כולי עלמא":  "everyone; the whole world",
    "תרוייהו":    "both of them",
    "חד מינייהו": "one of them",
    "האי":        "this (Aramaic)",
    "הני":        "these (Aramaic)",
    "הוא":        "he; it",
    "היא":        "she; it",
    "הם":         "they",
    "הן":         "they (f.)",
    "אנן":        "we (Aramaic)",
    "אנא":        "I (Aramaic)",
    "את":         "you (m.); with; sign of direct object",
    "לן":         "to us; for us",
    "לה":         "to her; to it",
    "ליה":        "to him; to it",
    "להו":        "to them",
    # ── Common Hebrew/Aramaic verbs — root forms ──────────────────────────────
    "אמר":        "to say; said",
    "ראה":        "to see; saw",
    "שמע":        "to hear; heard",
    "ידע":        "to know; knew",
    "עשה":        "to do; to make; did",
    "נתן":        "to give; gave",
    "הלך":        "to go; went",
    "בא":         "to come; came",
    "יצא":        "to go out; to leave; to exit",
    "נכנס":       "to enter; to go in",
    "ישב":        "to sit; to dwell; sat",
    "עמד":        "to stand; stood",
    "לקח":        "to take; took",
    "נשא":        "to carry; to marry; took; bore",
    "שם":         "to place; to put",
    "שאל":        "to ask; to borrow; asked",
    "ענה":        "to answer; answered",
    "חזר":        "to return; returned",
    "חזא":        "to see (Aramaic); saw",
    "אתא":        "to come (Aramaic); came",
    "אזל":        "to go (Aramaic); went",
    "יהב":        "to give (Aramaic); gave",
    "שרי":        "to begin; to permit; began",
    "סבר":        "to think; to reason; thought",
    "קם":         "to arise; to stand up; arose",
    "נפל":        "to fall; fell",
    "רצה":        "to want; to wish; wanted",
    "יכול":       "to be able; can; could",
    "צריך":       "to need; must; needs",
    "מצא":        "to find; found",
    "מכר":        "to sell; sold",
    "קנה":        "to buy; to acquire; bought",
    "שלח":        "to send; sent",
    "שחט":        "to slaughter (ritually); slaughtered",
    "אכל":        "to eat; ate",
    "שתה":        "to drink; drank",
    "כתב":        "to write; wrote",
    "קרא":        "to read; to call; read; called",
    "למד":        "to learn; to teach; learned",
    "לימד":       "to teach; taught",
    "פסק":        "to rule; to decide; ruled",
    "חשב":        "to think; to consider; to calculate",
    "ירד":        "to go down; to descend; descended",
    "עלה":        "to go up; to ascend; ascended",
    "נפק":        "to go out (Aramaic); went out",
    "עייל":       "to enter (Aramaic); entered",
    # ── Common verb infinitives (ל + infinitive construct) ────────────────────
    "לצאת":       "to go out; to leave; to exit",
    "לבוא":       "to come; to arrive",
    "לילך":       "to go; to walk",
    "ללכת":       "to go; to walk",
    "לעשות":      "to do; to make",
    "לתת":        "to give",
    "לשמוע":      "to hear; to listen",
    "לראות":      "to see; to look",
    "לדעת":       "to know",
    "לקחת":       "to take",
    "לשאול":      "to ask; to borrow",
    "לאכול":      "to eat",
    "לשתות":      "to drink",
    "לכתוב":      "to write",
    "לקרוא":      "to read; to call",
    "ללמוד":      "to learn; to study",
    "להביא":      "to bring",
    "לישב":       "to sit; to dwell",
    "לעמוד":      "to stand",
    "לשלם":       "to pay; to complete",
    "לחזור":      "to return; to repeat",
    "לשחוט":      "to slaughter (ritually)",
    "למכור":      "to sell",
    "לקנות":      "to buy; to acquire",
    "להוציא":     "to take out; to extract; to exempt",
    "להכניס":     "to bring in; to insert",
    "לחייב":      "to obligate; to find liable",
    "לפטור":      "to exempt; to release from obligation",
    "לאסור":      "to prohibit; to forbid",
    "להתיר":      "to permit; to allow",
    "לטמא":       "to make impure; to defile",
    "לטהר":       "to purify; to declare pure",
    "לאתויי":     "to include; to bring (Aramaic infinitive)",
    # ── Common participial / present-tense forms ──────────────────────────────
    "יוצא":       "going out; exits; leaves",
    "נכנס":       "entering; goes in",
    "הולך":       "going; walks",
    "בא":         "coming; comes",
    "עושה":       "doing; makes",
    "נותן":       "giving; gives",
    "אומר":       "saying; says",
    "רואה":       "seeing; sees",
    "שומע":       "hearing; listens",
    "יודע":       "knowing; knows",
    "יכול":       "able; can",
    "צריך":       "needed; must; requires",
    "רוצה":       "wanting; wants",
    "חייב":       "liable; obligated; owes",
    "אסור":       "forbidden; is prohibited",
    "מותר":       "permitted; is allowed",
    "פטור":       "exempt; is not liable",
    "מוכר":       "seller; selling",
    "קונה":       "buyer; buying; acquires",
    "שוחט":       "one who slaughters; slaughtering",
    "אוכל":       "eating; one who eats",
    "שותה":       "drinking; one who drinks",
    "כותב":       "writing; one who writes",
    "קורא":       "reading; calling; one who reads",
    "לומד":       "learning; studying",
    "מלמד":       "teaching; teacher",
    "מביא":       "bringing; one who brings",
    "מוציא":      "taking out; one who carries out",
    "מכניס":      "bringing in; one who carries in",
    "שולח":       "sending; one who sends",
    "שוכח":       "forgetting; one who forgets",
    "זוכר":       "remembering; one who remembers",
    "חוזר":       "returning; one who returns",
    "יורד":       "going down; descending",
    "עולה":       "going up; ascending; immigrant to Israel",
    # ── Common Aramaic verb forms ─────────────────────────────────────────────
    "קאמר":       "he says; is saying",
    "קאמרינן":    "we are saying",
    "אמרינן":     "we say",
    "תנינא":      "we have learned (in Mishnah)",
    "תנן":        "we have learned; the Mishnah taught",
    "שמעינן":     "we derive; we learn from this",
    "מתקיף":      "objects; raises a challenge",
    "מסייע":      "supports; aids",
    "פריך":       "raises an objection",
    "מפרק":       "resolves; answers",
    "אמר ליה":    "he said to him",
    "אמרה ליה":   "she said to him",
    "אמרו לו":    "they said to him",
    "אמר להו":    "he said to them",
    "חזינן":      "we see; we observe",
    "חזי":        "see! look! (imperative Aramaic)",
    "סבר":        "he thought; he reasoned",
    "סברי":       "they thought; they reasoned",
    "קסבר":       "he holds; he maintains (the opinion)",
    "קסברי":      "they hold; they maintain",
    "אזיל":       "he goes; he went (Aramaic)",
    "אתי":        "he comes; came (Aramaic)",
    "יהיב":       "he gives; gave (Aramaic)",
    "שקיל":       "he takes; took (Aramaic)",
    "נפיק":       "he goes out; went out (Aramaic)",
    "עייל":       "he enters; entered (Aramaic)",
    "שרי":        "he began; it is permitted (Aramaic)",
    "אמרה":       "she said; it said",
    "אמרו":       "they said",
    "אמרת":       "you said; she said",
    "אמרי":       "they say; I say (Aramaic)",
    "אמינא":      "I say; I said (Aramaic)",
    "ידעינן":     "we know",
    "ידע":        "he knows; he knew",
    "בעי":        "he asks; he inquires; he needs (Aramaic)",
    "בעינן":      "we need; we require",
    "יתיב":       "he sits; was sitting (Aramaic)",
    "קאי":        "he stands; is standing (Aramaic)",
    "אשכח":       "he found (Aramaic)",
    "אמטי":       "he brought to; arrived (Aramaic)",
}

# ── Regex patterns for distill() ─────────────────────────────────────────────
# Matches the start of a Talmudic citation.
# First char class includes Ḥ/Ṭ/Ṣ (used in Jastrow: Ḥull., Ṭar., etc.)
_CITATION_RE = re.compile(
    r'[A-ZḥḤṭṬṣṢẒ][a-zA-ZḥḤṭṬṣṢẒ]{1,8}\.\s+(?:[IVXLCDM]+|\d)'
    r'|(?<!\w)(?:Ib|Ibid)\.\s'
    r'|\ba\.\s*(?:fr|e|v)\b'
    r'|\bv\.\s+[א-ת]'
    r'|\bv\.\s+[A-Z]',
    re.UNICODE,
)
_LEAD_RE = re.compile(
    r'^(?:'
    r',\s*|—\s*'
    r'|\(b\.\s*h\.\)\s*|\(Hebr\.\)\s*|ch\.\s*'
    r'|(?:cmp\.\s*)?preced\.\)\s*'   # "preced.)" and "cmp. preced.)"
    r'|\)\s*[mf]\.\s*(?:;|pl\.)[^;]*?;\s*'  # ") m.; pl. ...;" grammar block
    r'|\)\s*'                          # bare leading ")"
    r')+'
)
# Sentence-end before a citation: ". " followed by capital or special chars
_SENT_END_RE = re.compile(r'\.\s+(?=[A-ZḥḤṭṬṣṢẒא-ת])')

# Patterns that signal the "definition" is actually a grammar label, not a gloss
_JUNK_GLOSS_RE = re.compile(
    r'^(?:inf|pr\.\s*n\.|pl\.\s*constr\.|m\.|f\.|pass\.|act\.|Af\.|Pa\.|Ithpe\.|Ithpa\.)',
    re.IGNORECASE
)


def strip_nikud(text: str) -> str:
    """Remove Hebrew vowel points and cantillation marks; trim whitespace."""
    return re.sub(r"[֑-ׇ]", "", text).strip()


def _finalize(stem: str) -> str:
    """Convert a stripped stem's last letter to its final form if applicable."""
    if stem and stem[-1] in _TO_FINAL:
        return stem[:-1] + _TO_FINAL[stem[-1]]
    return stem


def distill(defn: str) -> str:
    """Extract a short (≤55 char) plain-English gloss from a Jastrow definition.

    Strips citations, cross-references, etymology, and Talmudic examples,
    leaving only the core meaning suitable for display on a small screen.
    Returns an empty string if no clean gloss can be extracted.
    """
    s = defn.strip()

    # Pure cross-reference entry: ", v. X" — no gloss here
    if re.match(r'^,?\s*v\.\s', s):
        return ""

    # Strip leading noise (commas, em-dashes, language markers)
    s = _LEAD_RE.sub('', s).strip()

    # Strip leading Targ. citation block (Aramaic entries often open with one)
    s = re.sub(r'^Targ\.[A-Za-zḥḤ\s\.]+?(?=[a-z\[])', '', s).strip()

    # Strip leading etymology in parens: (contr. of X), (cmp. X), (= אֵי a. כָּא)
    m = re.match(r'^\(([^)]{1,120})\)\s*', s)
    if m and re.search(r'[א-ת]|cmp\.|contr\.|preced\.|denom\.', m.group(1)):
        s = s[m.end():].strip()

    # Extract bracket gloss: [engraving,] or [to be still,]
    bracket = ""
    m = re.match(r'^\[([^\]]{1,80})\]\.?\s*', s)
    if m:
        b = m.group(1).rstrip('.,').strip()
        if not re.search(r'[A-Z][a-z]+\.\s', b):  # skip if it's a citation
            bracket = b
        s = s[m.end():].strip()

    # Cut at the first Talmudic citation
    cm = _CITATION_RE.search(s)
    if cm:
        s = s[:cm.start()].strip()

    # Cut at sentence boundary (". " before capital/Hebrew — the definition
    # sentence ends and citations / examples begin)
    sm = _SENT_END_RE.search(s)
    if sm:
        s = s[:sm.start()].strip()

    # Cut at em-dash (separates sub-entries like "—ג׳ אשה letter of divorce")
    s = s.split('—')[0].strip()

    # Cut at semicolon (take primary meaning only)
    s = s.split(';')[0].strip()

    # Cut before grammatical annotations
    s = re.split(r'\bPl\.\s|\bSing\.\s|\bPart\.\s|\bInf\.\s', s)[0].strip()

    # Strip ANY trailing parenthetical: "value (in Greek writers: Mammon)"
    s = re.sub(r'\s*\([^)]+\)\s*$', '', s).strip()

    # Clean trailing punctuation
    s = s.rstrip('.,;:— ')

    # Reject grammar-label-only glosses (inf, pr. n., pl. constr., etc.)
    if s and _JUNK_GLOSS_RE.match(s):
        s = ""

    # Prefer the main text (s) over the bracket (which is usually etymology)
    gloss = s if s else bracket

    # Hard length limit
    if len(gloss) > 55:
        cut = gloss[:55].rfind(',')
        gloss = gloss[:cut].rstrip() if cut > 12 else gloss[:55].rstrip() + '…'

    return gloss


def _load() -> None:
    global _index, _tractate_sense, _abbreviations, _phrases
    if _index is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _index = json.load(f)
    if _tractate_sense is None:
        try:
            with open(_TSENSE_PATH, encoding="utf-8") as f:
                _tractate_sense = json.load(f)
        except FileNotFoundError:
            _tractate_sense = {}
    if _abbreviations is None:
        try:
            with open(_ABBREV_PATH, encoding="utf-8") as f:
                _abbreviations = json.load(f)
        except FileNotFoundError:
            _abbreviations = {}
    if _phrases is None:
        try:
            with open(_PHRASES_PATH, encoding="utf-8") as f:
                _phrases = json.load(f)
        except FileNotFoundError:
            _phrases = {}


def _exact(key: str) -> list:
    return _index.get(key, [])


def detect_language(entry: dict) -> str:
    """Classify an entry as hebrew / aramaic / both / unknown.

    Uses Jastrow's own notation:
      (b. h.) / (Hebr.) -> Biblical/Hebrew origin
      Targ. / ch.       -> Targumic/Chaldee (Aramaic)
    """
    defn = entry.get("def", "")
    hw = entry.get("hw", "")
    is_hebrew = "(b. h.)" in defn or "(Hebr.)" in defn
    is_aramaic = (
        " ch." in defn or defn.startswith("ch.")
        or "Targ." in defn or "Targ." in hw
    )
    if is_hebrew and is_aramaic:
        return "both"
    if is_hebrew:
        return "hebrew"
    if is_aramaic:
        return "aramaic"
    return "unknown"


def _follow_xrefs(entries: list) -> list:
    """Replace pure cross-reference entries (", v. X") with what they point to."""
    result = []
    for entry in entries:
        m = _XREF_RE.match(entry.get("def", ""))
        if not m:
            result.append(entry)
            continue
        targets = [strip_nikud(t).strip("., ") for t in m.group(1).split(",")]
        followed = False
        for target in targets:
            if len(target) >= 2:
                ref = _exact(target)
                if ref:
                    result.extend(ref)
                    followed = True
                    break
        if not followed:
            result.append(entry)   # keep original if target not found
    return result


def _candidates(word: str) -> tuple[list[str], list[str], list[str]]:
    """Return (suf_forms, pre_forms, ext_forms).

    suf_forms  — candidates where at least one suffix was stripped.
                 These are tried first: suffix-stripped roots are more
                 specific and suppress false positives from pure prefix paths
                 (e.g. תנאים → תנא via suffix beats נאים via ת-prefix).
    pre_forms  — candidates from prefix-stripping only (no suffix removed),
                 including vav-removal, second-level strips.
    ext_forms  — synthetic ה/א extensions tried last.
    """
    suf: list[str] = []
    pre: list[str] = []

    def _add_suf(stem: str) -> None:
        suf.append(stem)
        f = _finalize(stem)
        if f != stem:
            suf.append(f)

    def _add_pre(stem: str) -> None:
        pre.append(stem)
        f = _finalize(stem)
        if f != stem:
            pre.append(f)

    # Expand word into base forms: original + vav-stripped variants.
    # Non-original forms are added directly as pre candidates.
    #   שוחט  → שחט  (ו at position 1, Kal pe-vav)
    #   ואומר → אומר → אמר  (ו-prefix then pe-vav root)
    #   ושוחט → שוחט → שחט
    bases: list[str] = [word]

    if len(word) >= 3 and word[1] == "ו":
        form = word[0] + word[2:]
        _add_pre(form)
        bases.append(form)

    if word.startswith("ו") and len(word) >= 4:
        inner = word[1:]
        _add_pre(inner)
        bases.append(inner)
        if len(inner) >= 3 and inner[1] == "ו":
            form2 = inner[0] + inner[2:]
            _add_pre(form2)
            bases.append(form2)

    for base in bases:
        # --- Suffix stripping (results go into suf) ---
        for sfx in _SUFFIXES:
            if base.endswith(sfx) and len(base) - len(sfx) >= 2:
                stem = base[: -len(sfx)]
                _add_suf(stem)
                for pfx in _PREFIXES:
                    if stem.startswith(pfx) and len(stem) - len(pfx) >= 2:
                        _add_suf(stem[len(pfx):])
                # Kal pe-vav: ו in position 1 of the suffix-stripped stem
                if len(stem) >= 3 and stem[1] == "ו":
                    wv = stem[0] + stem[2:]
                    _add_suf(wv)
                    for pfx in _PREFIXES:
                        if wv.startswith(pfx) and len(wv) - len(pfx) >= 2:
                            _add_suf(wv[len(pfx):])
                # Hollow-root ו from positions 2–3
                if len(stem) >= 4:
                    for vpos in (2, 3):
                        if vpos < len(stem) and stem[vpos] == "ו":
                            nv = stem[:vpos] + stem[vpos + 1:]
                            if len(nv) >= 2:
                                _add_suf(nv)
                                for pfx in _PREFIXES:
                                    if nv.startswith(pfx) and len(nv) - len(pfx) >= 2:
                                        _add_suf(nv[len(pfx):])

        # --- Prefix-only stripping (results go into pre) ---
        for pfx in _PREFIXES:
            if base.startswith(pfx) and len(base) - len(pfx) >= 2:
                stripped = base[len(pfx):]
                _add_pre(stripped)
                if len(stripped) >= 3 and stripped[1] == "ו":
                    _add_pre(stripped[0] + stripped[2:])

    # Deduplicate suf, then pre (excluding what suf already claimed)
    seen: set = set()
    unique_suf: list[str] = []
    for c in suf:
        if c not in seen and c != word:
            seen.add(c)
            unique_suf.append(c)

    unique_pre: list[str] = []
    for c in pre:
        if c not in seen and c != word:
            seen.add(c)
            unique_pre.append(c)

    # Second-level prefix stripping applied to both groups
    second_pre: list[str] = []
    for c in list(unique_suf) + list(unique_pre):
        for pfx in _SAFE_PREFIXES:
            if c.startswith(pfx) and len(c) - len(pfx) >= 2:
                c2 = c[len(pfx):]
                for cand in (c2, _finalize(c2)):
                    if cand not in seen and cand != word:
                        seen.add(cand)
                        second_pre.append(cand)
    unique_pre.extend(second_pre)

    # Synthetic extensions: ה / א tried last
    ext: list[str] = []
    ext_seen: set = seen.copy()
    for c in unique_suf + unique_pre:
        for sfx in ("ה", "א"):
            x = c + sfx
            if not c.endswith(sfx) and x not in ext_seen and x != word:
                ext_seen.add(x)
                ext.append(x)

    return unique_suf, unique_pre, ext


def _explain(original: str, root: str) -> dict:
    """Best-effort morpheme decomposition: what prefix/suffix was stripped?"""
    # Case 1: root is a simple substring of original
    idx = original.find(root)
    if idx >= 0:
        return {"prefix": original[:idx], "root": root, "suffix": original[idx + len(root):]}
    # Case 2: a ו was removed from the root (Kal participle / hollow root)
    for vpos in range(1, len(root)):
        expanded = root[:vpos] + "ו" + root[vpos:]
        idx = original.find(expanded)
        if idx >= 0:
            return {"prefix": original[:idx], "root": root, "suffix": original[idx + len(expanded):]}
    # Case 3: an aleph/heh extension was added — strip it for comparison
    if root and root[-1] in "האו":
        idx = original.find(root[:-1])
        if idx >= 0:
            return {"prefix": original[:idx], "root": root, "suffix": original[idx + len(root) - 1:]}
    return {"prefix": "", "root": root, "suffix": ""}


def _resolve(key: str) -> tuple[list, str, dict]:
    """Core search. Returns (entries, match_type, morphology)."""
    # 1. Exact match
    result = _follow_xrefs(_exact(key))
    if result:
        return result, "exact", {}

    # 2. Suffix-stripped candidates (higher priority) then prefix-only, then extensions.
    # Sorting each group by length descending: longer stripped stems are more specific.
    suf_forms, pre_forms, ext_forms = _candidates(key)
    for candidate in (sorted(suf_forms, key=len, reverse=True) +
                      sorted(pre_forms, key=len, reverse=True) +
                      ext_forms):
        result = _follow_xrefs(_exact(candidate))
        if result:
            return result, "root", _explain(key, candidate)

    # 3. Starts-with fallback (user typed a partial root)
    matches = []
    for hw_key, entries in _index.items():
        if hw_key.startswith(key) and hw_key != key:
            matches.extend(entries)
        if len(matches) >= 5:
            break
    matches = _follow_xrefs(matches)
    if matches:
        return matches, "prefix", {}

    return [], "none", {}


def expand_abbreviation(word: str) -> dict | None:
    """If word looks like a Hebrew abbreviation (contains ״ or '), expand it.

    Returns {letters, full, en} or None if not recognised.
    """
    _load()
    # Normalise: strip nikud, remove gershayim characters (״ U+05F4, " U+0022, ' U+0027)
    stripped = strip_nikud(word)
    letters = re.sub(r'[״\'"]', '', stripped)
    if not letters or not re.search(r'[א-ת]', letters):
        return None
    entry = _abbreviations.get(letters)
    if entry:
        return {"letters": letters, **entry}
    return None


def lookup_phrase(text: str) -> dict | None:
    """Check if text is (or starts with) a known Talmudic phrase.

    Returns {phrase, meaning} or None.
    """
    _load()
    stripped = strip_nikud(text)
    if stripped in _phrases:
        return {"phrase": stripped, "meaning": _phrases[stripped]}
    # Partial: try first two words of text against phrase keys
    words = stripped.split()
    if len(words) >= 2:
        prefix = " ".join(words[:2])
        if prefix in _phrases:
            return {"phrase": prefix, "meaning": _phrases[prefix]}
        if len(words) >= 3:
            prefix3 = " ".join(words[:3])
            if prefix3 in _phrases:
                return {"phrase": prefix3, "meaning": _phrases[prefix3]}
    return None


def analyze(word: str, tractate: str = "") -> dict:
    """Full structured lookup — the recommended entry point for the pen.

    Returns:
      {
        "query":      original input string,
        "normalized": nikud-stripped form actually searched,
        "found":      bool,
        "match_type": "exact" | "root" | "prefix" | "none",
        "tractate":   tractate context used (empty = none),
        "context_sense": True if the entry was reordered for this tractate,
        "morphology": {"prefix", "root", "suffix"} — only present for root matches,
        "entries":    [ {"hw", "def", "lang"}, ... ],
      }
    """
    _load()
    key = strip_nikud(word)
    cache_key = (key, tractate)

    if cache_key in _cache:
        return _cache[cache_key]

    # Check quick-gloss overrides first (common Talmudic words Jastrow misses)
    quick = _QUICK_GLOSSES.get(key)

    entries, match_type, morphology = _resolve(key)
    tagged = [{**e, "lang": detect_language(e)} for e in entries]

    # ── Tractate-context reordering ─────────────────────────────────────────
    # If a tractate is specified and we have sense data for this word,
    # promote the tractate-specific entry to the front so its gloss is used.
    context_sense = False
    if tractate and tagged and key in _tractate_sense:
        sense_map = _tractate_sense[key]
        preferred_raw = sense_map.get(tractate)
        if preferred_raw is not None:
            # Support both old format (int) and new format ({index, confidence})
            preferred_idx = preferred_raw["index"] if isinstance(preferred_raw, dict) else preferred_raw
            if isinstance(preferred_idx, int) and preferred_idx < len(tagged):
                reordered = [tagged[preferred_idx]] + [
                    e for i, e in enumerate(tagged) if i != preferred_idx
                ]
                tagged = reordered
                context_sense = True

    # Build the short gloss: quick override > distilled Jastrow > empty
    if quick:
        gloss = quick
    elif tagged:
        gloss = distill(tagged[0]["def"])
    else:
        gloss = ""

    result = {
        "query":        word,
        "normalized":   key,
        "found":        bool(tagged) or bool(quick),
        "match_type":   match_type if tagged else ("quick" if quick else "none"),
        "tractate":     tractate,
        "context_sense": context_sense,
        "gloss":        gloss,
        "entries":      tagged,
    }
    if morphology:
        result["morphology"] = morphology
    _cache[cache_key] = result
    return result


def lookup(word: str, tractate: str = "") -> list:
    """Convenience: return just the matching entries (each with a 'lang' tag)."""
    return analyze(word, tractate)["entries"]
