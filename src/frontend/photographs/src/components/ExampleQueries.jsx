import React from 'react';
import { searchHref } from '../hooks/useHashRoute';
import './ExampleQueries.css';

// Enough suggestions for each way Auto can read a query to have one.
const SHOWN_QUERIES = 8;

const asExample = (entry) => (typeof entry === 'string' ? { query: entry } : entry);

function ExampleQueries({ queries, groups = [], uncataloged = true }) {
  if (!queries || queries.length === 0) {
    return null;
  }

  return (
    <div className="example-queries">
      <span className="example-queries-label">Try</span>
      {queries.slice(0, SHOWN_QUERIES).map(asExample).map(({ query, label }) => (
        <a key={query} className="example-query" href={searchHref(query, 1, groups, { uncataloged })}>
          {query}
          {label && <span className="example-query-label">{label}</span>}
        </a>
      ))}
    </div>
  );
}

export default ExampleQueries;
