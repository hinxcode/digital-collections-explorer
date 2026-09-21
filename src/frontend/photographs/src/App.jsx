import React, { useCallback, useEffect, useRef, useState } from 'react';
import SearchBar from './components/SearchBar';
import SearchResults from './components/SearchResults';
import ExampleQueries from './components/ExampleQueries';
import ImageGrid from './components/ImageGrid';
import ItemDetail from './components/ItemDetail';
import SiteFooter from './components/SiteFooter';
import { searchHref, useHashRoute } from './hooks/useHashRoute';
import { getCollection, getSample, searchByImage, searchByText } from './services/api';
import './App.css';

const WALL_SIZE = 60;
const RESULTS_PER_PAGE = 48;

function App() {
  const [route, navigate] = useHashRoute();
  const [collection, setCollection] = useState(null);
  const [wall, setWall] = useState([]);
  const [wallHasMore, setWallHasMore] = useState(false);
  const [wallIsLoading, setWallIsLoading] = useState(false);
  const wallSeed = useRef(Math.floor(Math.random() * 1e9));
  const [results, setResults] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadedImage, setUploadedImage] = useState(null);
  const searchInputRef = useRef(null);

  useEffect(() => {
    getCollection()
      .then(setCollection)
      .catch((loadError) => console.error('Failed to load the collection:', loadError));
  }, []);

  useEffect(() => {
    if (collection?.title) {
      document.title = collection.title;
    }
  }, [collection]);

  const extendWall = useCallback(() => {
    setWallIsLoading(true);
    getSample(WALL_SIZE, wallSeed.current, wall.length)
      .then(({ results: more, has_more: hasMoreImages }) => {
        setWall((shown) => [...shown, ...more]);
        setWallHasMore(hasMoreImages);
      })
      .catch((loadError) => console.error('Failed to load images:', loadError))
      .finally(() => setWallIsLoading(false));
  }, [wall.length]);

  useEffect(() => {
    if (route.name === 'home' && wall.length === 0 && !wallIsLoading) {
      extendWall();
    }
  }, [route.name, wall.length, wallIsLoading, extendWall]);

  useEffect(() => {
    const isTextSearch = route.name === 'search';
    const isImageSearch = route.name === 'image-search' && uploadedImage;
    if (!isTextSearch && !isImageSearch) {
      return undefined;
    }

    let isCurrent = true;
    setIsLoading(true);
    setError(null);
    if (isTextSearch) {
      setSearchQuery(route.query);
    }

    const request = isTextSearch
      ? searchByText(route.query, RESULTS_PER_PAGE, route.page)
      : searchByImage(uploadedImage, RESULTS_PER_PAGE, route.page);

    request
      .then((found) => {
        if (isCurrent) {
          setResults(found);
          setHasMore(found.length >= RESULTS_PER_PAGE);
        }
      })
      .catch(() => isCurrent && setError('The search failed. Please try again.'))
      .finally(() => isCurrent && setIsLoading(false));

    return () => {
      isCurrent = false;
    };
  }, [route.name, route.query, route.page, uploadedImage]);

  useEffect(() => {
    if (route.name === 'home') {
      setSearchQuery('');
    }
  }, [route.name]);

  useEffect(() => {
    if (route.name === 'image-search' && !uploadedImage) {
      navigate('#/');
    }
  }, [route.name, uploadedImage, navigate]);

  const handleSearchByText = useCallback((query) => {
    if (query.trim()) {
      navigate(searchHref(query.trim()));
    }
  }, [navigate]);

  const handleSearchByImage = useCallback((image) => {
    setUploadedImage(image);
    setSearchQuery('');
    navigate('#/image-search');
  }, [navigate]);

  const handleImageCleared = useCallback(() => {
    setUploadedImage(null);
    navigate('#/');
  }, [navigate]);

  const handlePageChanged = useCallback((change) => {
    const page = typeof change === 'function' ? change(route.page) : change;
    navigate(route.name === 'search'
      ? searchHref(route.query, page)
      : `#/image-search?page=${page}`);
  }, [navigate, route.name, route.query, route.page]);

  const isSearching = route.name === 'search' || route.name === 'image-search';
  const title = collection?.title || 'Digital Collection Explorer';

  return (
    <div className="App">
      <header className={`App-header ${route.name === 'home' ? '' : 'App-header-compact'}`}>
        <h1><a href="#/">{title}</a></h1>
        {route.name === 'home' && collection && (
          <>
            <p>{collection.description}</p>
            <p className="App-header-counts">
              {collection.objects.toLocaleString()} objects · {collection.images.toLocaleString()} images
              {collection.source_name ? ` · from ${collection.source_name}` : ''}
            </p>
          </>
        )}
      </header>

      <main className="App-main">
        {route.name !== 'item' && (
          <div className="search-controls">
            <SearchBar
              inputRef={searchInputRef}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              uploadedImage={route.name === 'image-search' ? uploadedImage : null}
              onSearchByText={handleSearchByText}
              onSearchByImage={handleSearchByImage}
              onClearImage={handleImageCleared}
            />
          </div>
        )}

        {route.name === 'home' && (
          <>
            <ExampleQueries queries={collection?.example_queries} />
            <section className="wall">
              <div className="wall-heading">
                <h2>Browse the collection</h2>
                <p>A random selection. Select any image to see it larger and find similar ones.</p>
              </div>
              <ImageGrid items={wall} />
              {wallHasMore && (
                <div className="wall-more">
                  <button type="button" onClick={extendWall} disabled={wallIsLoading}>
                    {wallIsLoading ? 'Loading…' : 'Show me more'}
                  </button>
                </div>
              )}
            </section>
          </>
        )}

        {isSearching && (
          <SearchResults
            items={results}
            isLoading={isLoading}
            error={error}
            currentPage={route.page}
            setCurrentPage={handlePageChanged}
            hasMore={hasMore}
            heading={route.name === 'search' ? `Results for “${route.query}”` : 'Images like the one you uploaded'}
          />
        )}

        {route.name === 'item' && <ItemDetail id={route.id} collection={collection} />}
      </main>

      <SiteFooter collection={collection} />
    </div>
  );
}

export default App;
