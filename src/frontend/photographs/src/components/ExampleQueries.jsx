import React from 'react';
import { searchHref } from '../hooks/useHashRoute';
import './ExampleQueries.css';

function ExampleQueries({ queries, groups = [] }) {
  if (!queries || queries.length === 0) {
    return null;
  }

  return (
    <div className="example-queries">
      <span className="example-queries-label">Try</span>
      {queries.map((query) => (
        <a key={query} className="example-query" href={searchHref(query, 1, groups)}>
          {query}
        </a>
      ))}
    </div>
  );
}

export default ExampleQueries;
