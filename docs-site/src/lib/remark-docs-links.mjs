/**
 * Remark plugin to rewrite internal docs links from relative .md paths
 * to docs-site route format: /docs/{slug}/
 *
 * Transforms:
 *   user/getting-started.md  → /docs/user/getting-started/
 *   dev/core/tools.md        → /docs/dev/core/tools/
 *   index.md                 → /docs/
 */
function remarkDocsLinks() {
  return function(tree) {
    visitLinks(tree);
  };
}

function visitLinks(node) {
  if (!node) return;

  // Handle link nodes [text](href)
  if (node.type === 'link' && typeof node.url === 'string') {
    node.url = rewriteLink(node.url);
  }

  // Handle definition nodes [id]: href
  if (node.type === 'definition' && typeof node.url === 'string') {
    node.url = rewriteLink(node.url);
  }

  // Handle image nodes
  if (node.type === 'image' && typeof node.url === 'string') {
    node.url = rewriteLink(node.url);
  }

  // Recurse children
  if (node.children) {
    node.children.forEach(visitLinks);
  }
}

function rewriteLink(href) {
  // Skip external links, anchors, absolute paths
  if (href.startsWith('http') || href.startsWith('#') || href.startsWith('/')) {
    return href;
  }

  // Match docs relative links: user/xxx.md, dev/xxx.md, index.md, etc.
  const docsPattern = /^(user|dev|superpowers)\/(.+)\.md$/;
  const match = href.match(docsPattern);
  if (match) {
    return `/docs/${match[1]}/${match[2]}/`;
  }

  // Match root index.md
  if (href === 'index.md') {
    return '/docs/';
  }

  // Match any other .md relative link
  const mdPattern = /^(.+)\.md$/;
  const mdMatch = href.match(mdPattern);
  if (mdMatch) {
    return `/docs/${mdMatch[1]}/`;
  }

  return href;
}

export default remarkDocsLinks;
