import React, { useMemo, useState } from 'react';
import { relatedImageUrl } from '../services/api';
import './RelatedSources.css';

// Tags beyond this many stay folded, so a long list does not push "Looks similar" out of view.
const TAGS_SHOWN = 20;
const COUNTS = [
  ['faves', 'fave', 'faves'],
  ['comments', 'comment', 'comments'],
  ['galleries', 'gallery', 'galleries'],
];

const counted = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

function RelatedPhoto({ related }) {
  const [showsAllTags, setShowsAllTags] = useState(false);
  const tags = related.tags || [];
  const shownTags = showsAllTags ? tags : tags.slice(0, TAGS_SHOWN);
  const counts = COUNTS.filter(([key]) => related.counts?.[key] > 0);
  const link = related.url
    ? { href: related.url, target: '_blank', rel: 'noopener noreferrer' }
    : null;

  return (
    <li className={`related-photo ${related.has_thumbnail ? '' : 'related-photo-text'}`}>
      {related.has_thumbnail && (
        <a className="related-photo-image" {...link} aria-hidden="true" tabIndex={-1}>
          <img src={relatedImageUrl(related.id)} alt="" loading="lazy" />
        </a>
      )}
      <div className="related-photo-facts">
        {link ? (
          <a className="related-photo-title" {...link}>{related.title || 'Untitled'}</a>
        ) : (
          <span className="related-photo-title">{related.title || 'Untitled'}</span>
        )}

        {counts.length > 0 && (
          <p className="related-photo-counts">
            {counts.map(([key, one, many]) => (
              <span key={key}>
                {key === 'comments' && link ? (
                  <a {...link}>{counted(related.counts[key], one, many)}</a>
                ) : counted(related.counts[key], one, many)}
              </span>
            ))}
          </p>
        )}

        {tags.length > 0 && (
          <>
            <ul className="related-photo-tags" aria-label="Tags">
              {shownTags.map((tag) => <li key={tag}>{tag}</li>)}
            </ul>
            {tags.length > TAGS_SHOWN && (
              <button
                type="button"
                className="link-button"
                onClick={() => setShowsAllTags(!showsAllTags)}
              >
                {showsAllTags ? 'Show fewer tags' : `Show all ${tags.length} tags`}
              </button>
            )}
          </>
        )}

        {related.rights && (
          <p className="related-photo-rights">
            {related.rights.url ? (
              <a href={related.rights.url} target="_blank" rel="noopener noreferrer">
                {related.rights.name}
              </a>
            ) : related.rights.name}
          </p>
        )}
      </div>
    </li>
  );
}

function RelatedSources({ related, sources }) {
  const bySource = useMemo(() => {
    const grouped = new Map();
    (related || []).forEach((entry) => {
      grouped.set(entry.source, [...(grouped.get(entry.source) || []), entry]);
    });
    return [...grouped.entries()];
  }, [related]);

  return bySource.map(([source, entries]) => {
    const about = sources?.[source] || {};
    return (
      <section key={source} className="related-sources">
        <h3>On {about.label || source}</h3>
        {about.note && <p className="item-detail-note">{about.note}</p>}
        <ul className="related-photos">
          {entries.map((entry) => <RelatedPhoto key={entry.id} related={entry} />)}
        </ul>
      </section>
    );
  });
}

export default RelatedSources;
