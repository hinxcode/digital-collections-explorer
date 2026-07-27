import React, { useState, useEffect } from 'react';
import { searchByText, searchByImage, getEmbeddingStats } from './services/api';
import SearchBar from './components/SearchBar';
import MediaResultsGrid from './components/MediaResultsGrid';
import './App.css';

const RESULTS_PER_PAGE = 30;

const SearchResults = React.memo(({ items, isLoading, hasSearched, error }) => {
  if (isLoading) {
    return (
      <div className="loading-indicator">
        <div className="spinner"></div>
        <p>Searching…</p>
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

  if (items.length > 0) {
    return (
      <div className="results-container">
        <MediaResultsGrid items={items} />
      </div>
    );
  }

  if (hasSearched) {
    return (
      <div className="no-results">
        <p>No clips found. Try a different search.</p>
      </div>
    );
  }

  return (
    <div className="welcome-message">
      <p>Search audio and video with natural language — e.g. &ldquo;ocean waves&rdquo;,
        &ldquo;dog barking&rdquo;, &ldquo;city traffic at night&rdquo;.</p>
      <p>You can also upload an image to find clips that look or sound like it.</p>
    </div>
  );
});

function App() {
  const [items, setItems] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchMode, setSearchMode] = useState('text'); // 'text' | 'image'
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState(null);
  const [embeddingCount, setEmbeddingCount] = useState(null);

  useEffect(() => {
    getEmbeddingStats().then((stats) => setEmbeddingCount(stats.count));
  }, []);

  const handleSearchByText = async (query) => {
    if (!query.trim()) {
      setError('Please enter a search term');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const results = await searchByText(query, RESULTS_PER_PAGE, 1);
      setItems(results);
      setHasSearched(true);
    } catch (err) {
      console.error('Error performing text search:', err);
      setError('Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchByImage = async (imageFile) => {
    if (!imageFile) {
      setError('Please choose an image');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const results = await searchByImage(imageFile, RESULTS_PER_PAGE, 1);
      setItems(results);
      setHasSearched(true);
    } catch (err) {
      console.error('Error performing image search:', err);
      setError('Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Multimedia Explorer</h1>
        <p>Search audio &amp; video across the collection with text or image</p>
      </header>

      <main className="App-main">
        <div className="search-controls">
          <SearchBar
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
            onSearchByText={handleSearchByText}
            onSearchByImage={handleSearchByImage}
          />
          {embeddingCount !== null && !hasSearched && (
            <p className="collection-count">
              {embeddingCount.toLocaleString()} items in this collection
            </p>
          )}
        </div>

        <SearchResults
          items={items}
          isLoading={isLoading}
          hasSearched={hasSearched}
          error={error}
        />
      </main>
    </div>
  );
}

export default App;
