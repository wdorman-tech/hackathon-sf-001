/**
 * v1 curated prompt set — a hand-written core spanning a 9-category taxonomy.
 * Categories let the leaderboard slice performance ("model X wins at diagrams,
 * Y at characters"). Later we LLM-augment each category for breadth (source:
 * 'generated'); these are the reproducible 'curated' core.
 */
export interface PromptSeed {
  text: string;
  category: Category;
}

export type Category =
  | "icon"
  | "object"
  | "scene"
  | "character"
  | "logo"
  | "diagram"
  | "dataviz"
  | "ui"
  | "pattern";

export const CATEGORY_LABELS: Record<Category, string> = {
  icon: "Icons & Glyphs",
  object: "Single Objects",
  scene: "Scenes & Illustrations",
  character: "Characters & Mascots",
  logo: "Logos & Wordmarks",
  diagram: "Technical Diagrams",
  dataviz: "Data Visualization",
  ui: "UI Mockups",
  pattern: "Patterns & Textures",
};

export const PROMPTS: PromptSeed[] = [
  // Icons & glyphs
  { text: "A minimalist line-art icon of a paper airplane", category: "icon" },
  { text: "A flat icon of a weather forecast: sun behind a rain cloud", category: "icon" },
  { text: "A settings gear icon with a small wrench overlaid", category: "icon" },

  // Single objects
  { text: "A steaming cup of coffee on a saucer, viewed from a slight angle", category: "object" },
  { text: "A vintage rotary telephone in teal", category: "object" },
  { text: "A potted monstera plant in a terracotta pot", category: "object" },

  // Scenes & illustrations
  { text: "A cozy reading nook by a rainy window at dusk", category: "scene" },
  { text: "A lighthouse on a rocky cliff under a starry night sky", category: "scene" },
  { text: "A bustling farmers market stall with fruit and flowers", category: "scene" },

  // Characters & mascots
  { text: "A friendly robot mascot waving hello", category: "character" },
  { text: "A cartoon fox wearing a scarf, sitting upright", category: "character" },
  { text: "An astronaut cat floating in space with a fishbowl helmet", category: "character" },

  // Logos & wordmarks
  { text: "A modern logo for a coffee roaster called 'Ember'", category: "logo" },
  { text: "A clean tech-startup logo combining a leaf and a circuit", category: "logo" },

  // Technical diagrams
  { text: "A labeled diagram of the water cycle", category: "diagram" },
  { text: "A simple flowchart of a user login process with a decision branch", category: "diagram" },
  { text: "A cross-section diagram of a layered Earth (crust, mantle, core)", category: "diagram" },

  // Data visualization
  { text: "A bar chart comparing quarterly revenue for four quarters", category: "dataviz" },
  { text: "A donut chart showing a budget split across five categories with a legend", category: "dataviz" },

  // UI mockups
  { text: "A music player app screen with album art, progress bar, and controls", category: "ui" },
  { text: "A weather widget card showing temperature, conditions, and a 3-day forecast", category: "ui" },

  // Patterns & textures
  { text: "A seamless geometric pattern of interlocking hexagons in two tones", category: "pattern" },
  { text: "A repeating pattern of tropical leaves and flowers", category: "pattern" },
];
