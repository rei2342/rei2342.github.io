/**
 * eyecatchPrompt.ts
 * 共通仕様 `config/eyecatch/sakura-v1.yaml` を読んで、
 * 画像AIへ渡すプロンプトへ変換する**アダプター**。
 *
 * **このファイルに人物設定・画風・禁止事項・比率を直接書かない。**
 * 値はすべて YAML から読む。直書きが増えたら、
 * scripts/test_eyecatch_spec.py の直書き検査が落ちる。
 *
 * Python側（scripts/eyecatch_spec.py）と**同じ順番・同じ見出し**で
 * 組み立てる。差が出たら差分検出テストが落ちる。
 *
 * noteツール側のリポジトリへは、このファイルをそのまま置き、
 * SPEC_PATH だけを向こうのパスへ変える。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse } from "yaml";

export const SPEC_PATH = resolve(
  __dirname,
  "../sakura-v1.yaml",
);

export type Spec = Record<string, any>;
export type Article = Record<string, any>;

export function loadSpec(path: string = SPEC_PATH): Spec {
  return parse(readFileSync(path, "utf-8"));
}

export function loadArticles(path: string): Spec {
  return parse(readFileSync(path, "utf-8"));
}

function bullets(items: string[], indent = "- "): string {
  return items.map((x) => `${indent}${x}`).join("\n");
}

/** 空白の詰め方を Python の " ".join(str.split()) と揃える */
function squash(s: string): string {
  return s.trim().split(/\s+/).join(" ");
}

export function buildPrompt(
  spec: Spec,
  article: Article,
  category: string,
): string {
  const c = spec.character;
  const s = spec.style;
  const comp = spec.composition;
  const neg = spec.negative_prompt;
  const colors = spec.category_colors;
  const accent = colors[category] ?? colors._default;
  const [w, h] = spec.master_size;
  const box = comp.text_safe_area.box;
  const fixed = c.fixed;

  const parts: string[] = [];

  parts.push(
    "CHARACTER (identical in every image of this site):\n" +
      bullets([
        fixed.ethnicity,
        fixed.age_impression,
        fixed.head_body_ratio,
        `${fixed.hair_length}, ${fixed.hair_color}, ${fixed.hair_texture}`,
        fixed.signature_accessory,
        `${fixed.clothing_base}, ${fixed.clothing_accent}`,
        fixed.expression,
        fixed.eye_treatment,
      ]),
  );

  parts.push("CHARACTER MUST NOT:\n" + bullets(c.forbidden));

  parts.push(
    "STYLE:\n" +
      bullets([
        s.medium,
        s.linework,
        s.shading,
        s.light,
        "base palette: " + s.base_colors.join(", "),
        "saturation: " + s.saturation,
      ]) +
      "\nNever: " + s.forbidden.join("; "),
  );

  parts.push(
    "COMPOSITION:\n" +
      bullets([
        `canvas exactly ${w} x ${h} px, ${spec.master_aspect_ratio}`,
        `place the subject ${comp.subject_anchor}`,
        `keep the rectangle x=${box[0]}-${box[2]}, y=${box[1]}-${box[3]} ` +
          `free of the subject and of strong contrast ` +
          `(${comp.text_safe_area.rule})`,
        comp.note_crop_safe.rule,
        `keep ${comp.edge_margin_px}px clear on every edge`,
        comp.scene_rule,
      ]),
  );

  const person = article.with_person
    ? "Show the character."
    : "Do NOT show any person. Objects, hands or the place only.";

  parts.push(
    "THIS ARTICLE:\n" +
      bullets([
        person,
        `camera: ${article.camera_distance}`,
        `accent colour: ${accent.name} (${accent.hex}), ` +
          `used on one small object only`,
        "scene: " + squash(article.scene),
      ]),
  );

  // 参照画像の使い分け。3枚を均等に混ぜない
  const ref = spec.reference_assets.directive;
  parts.push(
    "REFERENCES:\n" +
      (article.with_person ? ref.with_person : ref.without_person).trim(),
  );

  parts.push(
    "DO NOT INCLUDE:\n" + bullets(neg.forbidden_content) +
      "\n" + neg.always_append,
  );

  return parts.join("\n\n");
}

export function buildOverlayPlan(
  spec: Spec,
  article: Article,
  category: string,
) {
  const t = spec.text_overlay;
  const accent = spec.category_colors[category] ?? spec.category_colors._default;
  return {
    size: spec.blog_export.size,
    lead: { text: article.lead_text, ...t.lead },
    sub: { text: article.sub_text, ...t.sub },
    accent_hex: accent.hex,
    font_family: t.font_family,
    filename: article.filename,
  };
}

/** CLI: npx tsx eyecatchPrompt.ts <articlesYaml> <postIdOrSlug> */
if (require.main === module) {
  const [articlesPath, key] = process.argv.slice(2);
  const spec = loadSpec();
  const doc = loadArticles(articlesPath);
  const art = doc.articles.find(
    (x: Article) => String(x.post_id) === key || x.slug === key,
  );
  if (!art) {
    console.error(`記事が見つからない: ${key}`);
    process.exit(1);
  }
  process.stdout.write(buildPrompt(spec, art, doc.category) + "\n");
}
