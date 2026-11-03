import React, { useMemo } from 'react';
import './RelatedSources.css';

const COUNTS = [
  ['faves', 'fave', 'faves'],
  ['comments', 'comment', 'comments'],
];

const counted = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

function RelatedLink({ related }) {
  const title = related.title || 'Untitled';
  const counts = COUNTS.filter(([key]) => related.counts?.[key] > 0);

  return (
    <li>
      {related.url ? (
        <a href={related.url} target="_blank" rel="noopener noreferrer">{title}</a>
      ) : title}
      {counts.map(([key, one, many]) => (
        <span key={key} className="related-source-count">
          {counted(related.counts[key], one, many)}
        </span>
      ))}
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

  return bySource.map(([source, entries]) => (
    <div key={source} className="related-source">
      <p>Also on {sources?.[source]?.label || source}</p>
      <ul>
        {entries.map((entry) => <RelatedLink key={entry.id} related={entry} />)}
      </ul>
    </div>
  ));
}

export default RelatedSources;
