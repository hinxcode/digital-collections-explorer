import React from 'react';
import { hasMarkup, parseMarkup } from '../services/catalogText';
import './CatalogText.css';

const FORMATTING = {
  B: 'strong',
  EM: 'em',
  I: 'em',
  STRONG: 'strong',
  SUB: 'sub',
  SUP: 'sup',
  U: 'u',
};
const BLOCKS = new Set(['DIV', 'LI', 'P']);

function CatalogText({ text, links = false }) {
  if (!text || !hasMarkup(text)) {
    return text || null;
  }

  const render = (node, key) => {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    const children = [...node.childNodes].map(render);
    const href = node.getAttribute('href') || '';
    if (node.tagName === 'BR') {
      return <br key={key} />;
    }
    if (FORMATTING[node.tagName]) {
      return React.createElement(FORMATTING[node.tagName], { key }, children);
    }
    if (links && node.tagName === 'A' && /^https?:\/\//i.test(href)) {
      return (
        <a key={key} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
      );
    }
    if (BLOCKS.has(node.tagName)) {
      return <span key={key} className="catalog-text-block">{children}</span>;
    }
    return <React.Fragment key={key}>{children}</React.Fragment>;
  };

  return [...parseMarkup(text).childNodes].map(render);
}

export default CatalogText;
