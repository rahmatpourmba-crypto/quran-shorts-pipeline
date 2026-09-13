import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Fonts, ProceduralBackground} from './visuals';

const GOLD = '#E8B360';
const GOLD_LIGHT = '#FFDE96';
const WHITE = '#FFFFFF';

type TrendStyle = {
  palette?: 'gold' | 'emerald';
  contrast?: 'deep' | 'soft';
  text_scale?: number;
  max_words?: number;
  glow?: 'strong' | 'soft';
  gold_accents?: number;
  center_bias?: number;
  features_avg?: Record<string, number>;
};

const LANG_LABEL: Record<string, string> = {
  en: 'English',
  ar: 'العربية',
  fa: 'فارسی',
  ku: 'کوردی',
};

const BRAND_TOP: Record<string, string> = {
  en: 'Quran Recitation · Peace',
  ar: 'تلاوة القرآن · راحة النفس',
  fa: 'تلاوت قرآن · آرامش',
  ku: 'قرئان خوێندن · ئارامی',
};

const BRAND_BOTTOM: Record<string, string> = {
  en: 'Subscribe · Like · Peace 🌿',
  ar: 'اشترك · أعجبك · راحة 🌿',
  fa: 'اشتراک · لایک · آرامش 🌿',
  ku: 'سەبسکرایب · لایک · ئارامی 🌿',
};

const CTAS: Record<string, string> = {
  en: 'Peace for your heart · Subscribe',
  ar: 'سكينة لقلبك · اشترك',
  fa: 'آرامش برای قلبت · دنبال کن',
  ku: 'ئارامی بۆ دڵت · سەبسکرایب',
};

type Item = {
  code: string;
  surahName: string;
  surahEn: string;
  ayahNum: number;
  arabic: string;
  fa: string;
  en: string;
};

export const TrendThumbnail: React.FC<{items: Item[]; hook?: string; surahMsg?: string; style?: TrendStyle; lang?: 'en' | 'ar' | 'fa' | 'ku'}> = ({items, hook, surahMsg, style, lang = 'fa'}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const f = items[0];
  const last = items[items.length - 1];
  const aria = (f?.arabic || '…').split('\n')[0];
  // per-language headline, kept meaningful (never chopped mid-sentence):
  //   en -> curated english surah message (or en ayah)  ar -> arabic hook
  //   fa -> persian translation of the ayah             ku -> hook/fa fallback
  const stripBasmala = (s: string) => {
    const parts = s.trim().split(' ');
    return parts[0] && parts[0].includes('بِسْمِ') ? parts.slice(4).join(' ') : s;
  };
  const hookSource =
    lang === 'en' ? (surahMsg || f?.en || hook || aria) :
    lang === 'ar' ? (hook || stripBasmala(aria)) :
    lang === 'ku' ? (hook || f?.fa || aria) :
    (f?.fa || hook || aria);
  const baseMax = style?.max_words && style.max_words > 1 ? style.max_words : 3;
  const maxWords = lang === 'en' ? Math.max(baseMax, 4) : (lang === 'ar' ? 10 : 8);
  const hookText = hookSource.split(' ').slice(0, maxWords).join(' ');
  const faShort = (f?.fa || 'تلاوت قرآن').split(' ').slice(0, 5).join(' ');
  const subLine =
    lang === 'en'
      ? `${f?.surahEn ?? ''} ${f?.ayahNum ?? ''} · The Quran, every day`
      : lang === 'ar'
      ? `${f?.surahName ?? ''} ${f?.ayahNum ?? ''} · تلاوة هادئة`
      : lang === 'ku'
      ? (f?.fa ? faShort : 'تلاوت قرآن')
      : `${f?.surahEn ?? ''} ${f?.ayahNum ?? ''} · هر روز یک آیه`;
  const hlen = hookText.length;
  const textScale = style?.text_scale ?? 1.0;
  const hookSize = (hlen <= 6 ? height * 0.3 : hlen <= 10 ? height * 0.225 : hlen <= 18 ? height * 0.16 : height * 0.13) * textScale;
  const pop = interpolate(frame, [0, 18], [0.92, 1], {easing: undefined, extrapolateRight: 'clamp'});
  const fade = interpolate(frame, [0, 14], [0, 1], {extrapolateRight: 'clamp'});
  const lil =
    lang === 'en'
      ? (f ? `${f.surahEn}${last?.ayahNum && last.ayahNum !== f.ayahNum ? ` ${f.ayahNum}-${last.ayahNum}` : ` ${f.ayahNum}`}` : '')
      : lang === 'ar'
      ? (f ? `${f.surahName}  ${f.ayahNum}` : '')
      : `${f?.surahEn ?? ''} ${f?.ayahNum ?? ''}`;
  const sub = (hlen <= 6 ? height * 0.048 : height * 0.04) * textScale;
const isGold = (style?.palette ?? 'gold') === 'gold';
const isDeep = (style?.contrast ?? 'deep') === 'deep';
const strongGlow = (style?.glow ?? 'strong') === 'strong';
const accent = isGold ? GOLD : '#7FD6A7';
const accentLight = isGold ? GOLD_LIGHT : '#DFF6E8';
// bold web-safe sans for English readability (Amiri/Vazirmatn render too thin)
const EN_FONT = '"Segoe UI", "Arial Black", system-ui, sans-serif';
// strong English headline colors (trend trick: bold cold/red text on warm bg)
const EN_COLOR = '#C9E6FF';          // ice blue-white
const EN_GLOW = 'rgba(120,190,255,0.9)';
const GLOW_COLOR = lang === 'en' ? EN_GLOW : `${accent}99`;
  const bgIndex = isGold ? 0 : 1; // golden night vs emerald deep
  const overlayDark = isDeep
    ? 'linear-gradient(180deg, rgba(5,7,12,0.02) 0%, rgba(5,7,12,0.42) 55%, rgba(5,7,12,0.85) 100%)'
    : 'linear-gradient(180deg, rgba(5,7,12,0.02) 0%, rgba(5,7,12,0.24) 50%, rgba(5,7,12,0.55) 100%)';
  const dir = lang === 'en' || lang === 'ku' ? 'ltr' : 'rtl';

  return (
    <AbsoluteFill style={{backgroundColor: '#05070c'}}>
      <ProceduralBackground index={isGold ? 0 : 1} />

      {/* dark anchor for text contrast */}
      <AbsoluteFill style={{background: overlayDark}} />
      <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 46%, rgba(0,0,0,0) 40%, rgba(5,7,12,0.${isDeep ? 55 : 38}) 100%)`}} />

      {/* premium inner frame + top light beam */}
      <AbsoluteFill style={{pointerEvents: 'none', border: `1.5px solid ${accent}66`, margin: '2.2%', borderRadius: 18}} />
      <AbsoluteFill style={{pointerEvents: 'none', border: `1px solid ${accentLight}40`, margin: '3.5%', borderRadius: 12}} />
      <AbsoluteFill style={{background: `radial-gradient(120% 70% at 50% -8%, ${accent}2e 0%, rgba(0,0,0,0) 55%)`}} />

      {/* consistent brand strip — top */}
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: height * 0.045}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 12, background: 'rgba(5,7,12,0.55)', border: `1.5px solid ${accent}88`, borderRadius: 60, padding: `${height * 0.008}px ${width * 0.024}px`}}>
          <div style={{width: height * 0.022, height: height * 0.022, borderRadius: '50%', background: isGold ? 'radial-gradient(circle, #FFDE96, #B27B21)' : 'radial-gradient(circle, #DFF6E8, #1E7A52)', border: `1px solid ${accentLight}`, boxShadow: `0 0 12px ${accent}99`}} />
          <div style={{fontFamily: Fonts.sans, fontWeight: 800, fontSize: height * 0.034, color: accentLight, letterSpacing: 1, whiteSpace: 'nowrap'}}>
            {BRAND_TOP[lang]}
          </div>
        </div>
      </AbsoluteFill>

      {/* single focal point: the hook */}
      <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', transform: `scale(${pop})`, opacity: fade, padding: '0 4%'}}>
        <div style={{
          fontFamily: lang === 'en' ? EN_FONT : Fonts.quran,
          fontWeight: lang === 'en' ? 900 : 700,
          fontSize: hookSize,
          color: lang === 'en' ? EN_COLOR : WHITE,
          textAlign: 'center',
          direction: dir,
          lineHeight: 1.2,
          letterSpacing: lang === 'en' ? 1 : 0,
          textTransform: lang === 'en' ? 'uppercase' : 'none',
          filter: strongGlow ? `drop-shadow(0 0 22px ${GLOW_COLOR})` : `drop-shadow(0 0 10px ${GLOW_COLOR})`,
          textShadow: '0 2px 0 rgba(5,7,12,1), 0 4px 0 rgba(5,7,12,0.95), 0 10px 24px rgba(0,0,0,0.9)',
        }}>
          {hookText}
        </div>

        {/* slim accent divider with pulse */}
        <div style={{width: width * 0.2, height: height * 0.009, background: `linear-gradient(90deg, transparent, ${accentLight}, transparent)`, borderRadius: 4, marginTop: height * 0.028, boxShadow: `0 0 18px ${accentLight}e6`}} />

        {/* surah badge — the lefthand content anchor */}
        <div style={{display: 'flex', alignItems: 'center', gap: 16, marginTop: height * 0.03}}>
          <div style={{width: height * 0.09, height: height * 0.09, borderRadius: '50%', background: `${accent}47`, border: `3px solid ${accent}`, alignItems: 'center', justifyContent: 'center', display: 'flex', boxShadow: `0 0 26px ${accent}73`}}>
            <div style={{width: 0, height: 0, borderLeft: width * 0.034, borderRight: 0, borderTop: width * 0.019, borderBottom: width * 0.019, borderLeftColor: accentLight, borderTopColor: 'transparent', borderBottomColor: 'transparent', marginLeft: width * 0.004}} />
          </div>
          <div style={{fontFamily: Fonts.sans, fontWeight: 900, fontSize: height * 0.09, color: WHITE, textShadow: `0 4px 16px rgba(0,0,0,0.9), 0 0 34px ${accent}99`, letterSpacing: 1}}>
            {lil}
          </div>
        </div>

        {/* short benefit line (4 words) */}
        <div style={{fontFamily: Fonts.fa, fontWeight: 800, fontSize: sub, color: '#FDF4DE', textAlign: 'center', direction: dir, marginTop: height * 0.03, textShadow: '0 3px 10px rgba(0,0,0,0.85)'}}>
          {subLine}
        </div>
      </AbsoluteFill>

      {/* consistent brand strip — bottom */}
      <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: height * 0.045}}>
        <div style={{fontFamily: Fonts.fa, fontWeight: 900, fontSize: height * 0.04, color: WHITE, background: isGold ? 'linear-gradient(135deg, rgba(199,142,38,0.75), rgba(232,179,96,0.85))' : 'linear-gradient(135deg, rgba(23,110,74,0.8), rgba(97,190,142,0.9))', border: `2px solid ${accentLight}`, padding: `${height * 0.012}px ${width * 0.03}px`, borderRadius: 50, boxShadow: `0 6px 26px rgba(0,0,0,0.55), 0 0 34px ${accentLight}66`, whiteSpace: 'nowrap'}}>
          {BRAND_BOTTOM[lang]}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};