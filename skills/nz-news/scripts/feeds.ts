export type FeedDefinition = {
  id: string;
  name: string;
  url: string;
  format: 'rss' | 'atom';
  category?: string;
};

export type NewsItem = {
  title: string;
  url: string;
  published: Date;
  source: string;
  sourceId: string;
  summary?: string;
};

export type FeedResult = {
  feed: FeedDefinition;
  items: NewsItem[];
  ok: boolean;
  error?: string;
  durationMs: number;
};

export const FEEDS: FeedDefinition[] = [
  { id: 'herald', name: 'NZ Herald', url: 'https://rss.nzherald.co.nz/rss/xml/nzhrsscid_000000001.xml', format: 'rss' },
  { id: 'stuff', name: 'Stuff', url: 'https://www.stuff.co.nz/rss', format: 'atom' },
  { id: 'rnz', name: 'RNZ', url: 'https://www.rnz.co.nz/rss/news.xml', format: 'rss' },
  { id: 'rnz-politics', name: 'RNZ Politics', url: 'https://www.rnz.co.nz/rss/political.xml', format: 'rss', category: 'politics' },
  { id: 'rnz-business', name: 'RNZ Business', url: 'https://www.rnz.co.nz/rss/business.xml', format: 'rss', category: 'business' },
  { id: 'rnz-national', name: 'RNZ National', url: 'https://www.rnz.co.nz/rss/national.xml', format: 'rss', category: 'national' },
  { id: 'rnz-world', name: 'RNZ World', url: 'https://www.rnz.co.nz/rss/world.xml', format: 'rss', category: 'world' },
  { id: 'rnz-sport', name: 'RNZ Sport', url: 'https://www.rnz.co.nz/rss/sport.xml', format: 'rss', category: 'sport' },
  { id: 'rnz-te-ao-maori', name: 'RNZ Te Ao Māori', url: 'https://www.rnz.co.nz/rss/te-ao-maori.xml', format: 'rss', category: 'te-ao-maori' },
  { id: 'newsroom', name: 'Newsroom', url: 'https://www.newsroom.co.nz/rss', format: 'rss' },
  { id: 'spinoff', name: 'The Spinoff', url: 'https://thespinoff.co.nz/feed', format: 'atom' },
  { id: 'interest', name: 'Interest.co.nz', url: 'https://www.interest.co.nz/rss', format: 'rss' },
];

/** Primary sources (excludes RNZ category sub-feeds to avoid duplicate stories) */
export const PRIMARY_FEED_IDS = ['herald', 'stuff', 'rnz', 'newsroom', 'spinoff', 'interest'];

function decodeEntities(text: string): string {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

function stripCdata(text: string): string {
  return text.replace(/^\s*<!\[CDATA\[([\s\S]*?)\]\]>\s*$/, '$1');
}

function extractTag(xml: string, tag: string): string {
  const pattern = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, 'i');
  const match = xml.match(pattern);
  if (!match) return '';
  return decodeEntities(stripCdata(match[1].trim()));
}

function extractAttr(xml: string, tag: string, attr: string): string {
  const pattern = new RegExp(`<${tag}[^>]*?${attr}="([^"]*)"`, 'i');
  const match = xml.match(pattern);
  return match ? decodeEntities(match[1]) : '';
}

function parseDate(raw: string): Date {
  if (!raw) return new Date(0);
  // Interest.co.nz uses "10th Apr 26, 4:12pm" — try standard first
  const standard = new Date(raw);
  if (!Number.isNaN(standard.getTime())) return standard;
  // Try Interest.co.nz format: "10th Apr 26, 4:12pm"
  const interestMatch = raw.match(/(\d+)\w*\s+(\w+)\s+(\d+),\s*(\d+):(\d+)(am|pm)/i);
  if (interestMatch) {
    const [, day, month, year, hours, minutes, ampm] = interestMatch;
    const fullYear = Number(year) < 100 ? 2000 + Number(year) : Number(year);
    let h = Number(hours);
    if (ampm.toLowerCase() === 'pm' && h < 12) h += 12;
    if (ampm.toLowerCase() === 'am' && h === 12) h = 0;
    const dateStr = `${day} ${month} ${fullYear} ${h}:${minutes}:00 +1200`;
    const parsed = new Date(dateStr);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return new Date(0);
}

function parseRssItems(xml: string, feed: FeedDefinition): NewsItem[] {
  const items: NewsItem[] = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/gi;
  let match: RegExpExecArray | null;
  while ((match = itemRegex.exec(xml)) !== null) {
    const block = match[1];
    const title = extractTag(block, 'title');
    const link = extractTag(block, 'link');
    const pubDate = extractTag(block, 'pubDate');
    const description = extractTag(block, 'description');
    if (title && link) {
      items.push({
        title,
        url: link,
        published: parseDate(pubDate),
        source: feed.name,
        sourceId: feed.id,
        summary: description || undefined,
      });
    }
  }
  return items;
}

function parseAtomItems(xml: string, feed: FeedDefinition): NewsItem[] {
  const items: NewsItem[] = [];
  const entryRegex = /<entry>([\s\S]*?)<\/entry>/gi;
  let match: RegExpExecArray | null;
  while ((match = entryRegex.exec(xml)) !== null) {
    const block = match[1];
    const title = extractTag(block, 'title');
    const link = extractAttr(block, 'link', 'href');
    const published = extractTag(block, 'published') || extractTag(block, 'updated');
    const summary = extractTag(block, 'summary');
    if (title && link) {
      items.push({
        title,
        url: link,
        published: parseDate(published),
        source: feed.name,
        sourceId: feed.id,
        summary: summary || undefined,
      });
    }
  }
  return items;
}

export async function fetchFeed(feed: FeedDefinition): Promise<FeedResult> {
  const start = Date.now();
  try {
    const response = await fetch(feed.url, {
      signal: AbortSignal.timeout(10_000),
      headers: { 'User-Agent': 'nz-news-cli/1.0' },
    });
    if (!response.ok) {
      return { feed, items: [], ok: false, error: `HTTP ${response.status}`, durationMs: Date.now() - start };
    }
    const xml = await response.text();
    const items = feed.format === 'atom' ? parseAtomItems(xml, feed) : parseRssItems(xml, feed);
    return { feed, items, ok: true, durationMs: Date.now() - start };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { feed, items: [], ok: false, error: message, durationMs: Date.now() - start };
  }
}

export async function fetchFeeds(feedIds?: string[]): Promise<FeedResult[]> {
  const selected = feedIds
    ? FEEDS.filter((f) => feedIds.includes(f.id))
    : FEEDS.filter((f) => PRIMARY_FEED_IDS.includes(f.id));
  return Promise.all(selected.map(fetchFeed));
}

export function deduplicateItems(items: NewsItem[]): NewsItem[] {
  const seen = new Map<string, NewsItem>();
  for (const item of items) {
    // Deduplicate by normalised title
    const key = item.title.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const existing = seen.get(key);
    if (!existing || item.published > existing.published) {
      seen.set(key, item);
    }
  }
  return [...seen.values()];
}

export function sortByDate(items: NewsItem[]): NewsItem[] {
  return [...items].sort((a, b) => b.published.getTime() - a.published.getTime());
}

export function filterByKeyword(items: NewsItem[], keyword: string): NewsItem[] {
  const lower = keyword.toLowerCase();
  return items.filter(
    (item) =>
      item.title.toLowerCase().includes(lower) ||
      (item.summary?.toLowerCase().includes(lower) ?? false),
  );
}
