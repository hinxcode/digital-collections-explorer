import React from 'react';
import ImageGrid from './ImageGrid';
import Pagination from './Pagination';
import './SearchResults.css';

const SearchResults = React.memo(({
  items,
  isLoading,
  error,
  currentPage,
  setCurrentPage,
  hasMore,
  heading,
}) => {
  if (isLoading) {
    return (
      <div className="loading-indicator">
        <div className="spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-message">
        <p>{error}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="no-results">
        <p>Nothing matched. Try describing what the picture looks like.</p>
      </div>
    );
  }

  return (
    <div className="gallery-container">
      <div className="results-heading">
        <h2>{heading}</h2>
        <p>
          Each object appears once. A number such as +3 means there are more photos of
          it. Ranked by an AI model, best matches first.
        </p>
      </div>
      <ImageGrid items={items} />
      <Pagination
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        hasMore={hasMore}
        isLoading={isLoading}
      />
    </div>
  );
});

export default SearchResults;
