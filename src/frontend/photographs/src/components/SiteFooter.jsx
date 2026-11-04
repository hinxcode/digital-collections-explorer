import React from 'react';
import './SiteFooter.css';

const DEFAULT_LINKS = [
  { label: 'How this works (paper)', url: 'https://doi.org/10.1017/chr.2025.10017' },
  { label: 'Source code', url: 'https://github.com/L4CCH/digital-collections-explorer' },
];

function SiteFooter({ collection }) {
  const links = collection?.links?.length ? collection.links : DEFAULT_LINKS;

  return (
    <footer className="site-footer">
      <p>
        Search results and similar images are ranked by an AI model that looks at the
        pictures themselves. It can be wrong, and it can reflect biases in the data it
        learned from. The catalog record at the source is the authority on every object.
      </p>
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
