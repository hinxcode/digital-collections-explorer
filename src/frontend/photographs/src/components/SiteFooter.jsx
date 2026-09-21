import React from 'react';
import './SiteFooter.css';

const DEFAULT_LINKS = [
  { label: 'How this works (paper)', url: 'https://arxiv.org/abs/2507.00961' },
  { label: 'Source code', url: 'https://github.com/hinxcode/digital-collections-explorer' },
];

const indexLine = (collection) => {
  const { images, index } = collection || {};
  if (!images || !index?.model_name) {
    return null;
  }
  const builtOn = index.built_at
    ? ` on ${new Date(index.built_at).toLocaleDateString('en', { year: 'numeric', month: 'long', day: 'numeric' })}`
    : '';
  return `${images.toLocaleString()} images indexed${builtOn} with ${index.model_name}.`;
};

function SiteFooter({ collection }) {
  const links = collection?.links?.length ? collection.links : DEFAULT_LINKS;
  const indexed = indexLine(collection);

  return (
    <footer className="site-footer">
      <p>
        Search results and similar images are ranked by an AI model that looks at the
        pictures themselves. It can be wrong, and it can reflect biases in the data it
        learned from. The catalog record at the source is the authority on every object.
      </p>
      {indexed && <p className="site-footer-index">{indexed}</p>}
      <ul>
        {links.map((link) => (
          <li key={link.url}>
            <a href={link.url} target="_blank" rel="noopener noreferrer">{link.label}</a>
          </li>
        ))}
      </ul>
    </footer>
  );
}

export default SiteFooter;
