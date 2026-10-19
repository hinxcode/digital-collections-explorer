import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import SearchBar from './components/SearchBar';
import SearchResults from './components/SearchResults';
import ExampleQueries from './components/ExampleQueries';
import GroupFilter from './components/GroupFilter';
import ImageGrid from './components/ImageGrid';
import ItemDetail from './components/ItemDetail';
import ModeToggle from './components/ModeToggle';
import SearchNotice from './components/SearchNotice';
import SiteFooter from './components/SiteFooter';
import {
  homeHref, imageSearchHref, searchHref, useHashRoute,
} from './hooks/useHashRoute';
import { getCollection, getSample, searchByImage, searchByText } from './services/api';
import './App.css';

const WALL_SIZE = 60;
const RESULTS_PER_PAGE = 48;

function App() {
  const [route, navigate, canGoBack] = useHashRoute();
  const [collection, setCollection] = useState(null);
  const [wall, setWall] = useState([]);
  const [wallHasMore, setWallHasMore] = useState(false);
  const [wallIsLoading, setWallIsLoading] = useState(false);
  const [wallFailed, setWallFailed] = useState(false);
  const wallSeed = useRef(Math.floor(Math.random() * 1e9));
  const [results, setResults] = useState([]);
  const [searchInfo, setSearchInfo] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadedImage, setUploadedImage] = useState(null);
  const searchInputRef = useRef(null);
  const groupsKey = (route.groups || []).join(',');
  const selectedGroups = useMemo(() => groupsKey.split(',').filter(Boolean), [groupsKey]);
  const wallGroups = useRef(groupsKey);
  const groupLabels = useMemo(
    () => Object.fromEntries((collection?.groups || []).map((group) => [group.id, group.label])),
    [collection],
  );

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
    setWallFailed(false);
    getSample(WALL_SIZE, wallSeed.current, wall.length, selectedGroups)
      .then(({ results: more, has_more: hasMoreImages }) => {
        if (wallGroups.current === groupsKey) {
          setWall((shown) => [...shown, ...more]);
          setWallHasMore(hasMoreImages);
        }
      })
      .catch((loadError) => {
        console.error('Failed to load images:', loadError);
        setWallFailed(true);
      })
      .finally(() => setWallIsLoading(false));
  }, [wall.length, groupsKey, selectedGroups]);

  useEffect(() => {
    if (route.name === 'home' && wallGroups.current !== groupsKey) {
      wallGroups.current = groupsKey;
      setWall([]);
      setWallHasMore(false);
      setWallFailed(false);
    }
  }, [route.name, groupsKey]);

  useEffect(() => {
    if (route.name === 'home' && wall.length === 0 && !wallIsLoading && !wallFailed) {
      extendWall();
    }
  }, [route.name, wall.length, wallIsLoading, wallFailed, extendWall]);

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
      ? searchByText(route.query, RESULTS_PER_PAGE, route.page, selectedGroups, {
        mode: route.mode,
        exact: route.exact,
      })
      : searchByImage(uploadedImage, RESULTS_PER_PAGE, route.page, selectedGroups);

    request
      .then(({ results: found, search }) => {
        if (isCurrent) {
          setResults(found);
          setSearchInfo(search);
          setHasMore(found.length >= RESULTS_PER_PAGE);
        }
      })
      .catch((searchError) => {
        if (isCurrent) {
          setError(searchError.visitorMessage || 'The search failed. Please try again.');
        }
      })
      .finally(() => isCurrent && setIsLoading(false));

    return () => {
      isCurrent = false;
    };
  }, [route.name, route.query, route.page, route.mode, route.exact, uploadedImage, selectedGroups]);

  useEffect(() => {
    if (route.name === 'home') {
      setSearchQuery('');
    }
  }, [route.name]);

  useEffect(() => {
    if (route.name === 'image-search' && !uploadedImage) {
      navigate(homeHref(selectedGroups));
    }
  }, [route.name, uploadedImage, navigate, selectedGroups]);

  const handleSearchByText = useCallback((query) => {
    if (query.trim()) {
      navigate(searchHref(query.trim(), 1, selectedGroups));
    }
  }, [navigate, selectedGroups]);

  const handleSearchByImage = useCallback((image) => {
    setUploadedImage(image);
    setSearchQuery('');
    navigate(imageSearchHref(1, selectedGroups));
  }, [navigate, selectedGroups]);

  const handleImageCleared = useCallback(() => {
    setUploadedImage(null);
    navigate(homeHref(selectedGroups));
  }, [navigate, selectedGroups]);

  const handlePageChanged = useCallback((change) => {
    const page = typeof change === 'function' ? change(route.page) : change;
    navigate(route.name === 'search'
      ? searchHref(route.query, page, selectedGroups, { mode: route.mode, exact: route.exact })
      : imageSearchHref(page, selectedGroups));
  }, [navigate, route.name, route.query, route.page, route.mode, route.exact, selectedGroups]);

  const handleGroupsChanged = useCallback((groups) => {
    if (route.name === 'search') {
      navigate(searchHref(route.query, 1, groups, { mode: route.mode, exact: route.exact }));
    } else if (route.name === 'image-search') {
      navigate(imageSearchHref(1, groups));
    } else {
      navigate(homeHref(groups));
    }
  }, [navigate, route.name, route.query, route.mode, route.exact]);

  const handleModeChanged = useCallback((mode) => {
    navigate(searchHref(route.query, 1, selectedGroups, { mode, exact: route.exact }));
  }, [navigate, route.query, route.exact, selectedGroups]);

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
            <div className="search-column">
              <SearchBar
                inputRef={searchInputRef}
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
                uploadedImage={route.name === 'image-search' ? uploadedImage : null}
                onSearchByText={handleSearchByText}
                onSearchByImage={handleSearchByImage}
                onClearImage={handleImageCleared}
              />
              <div className="search-options">
                <GroupFilter
                  groups={collection?.groups}
                  label={collection?.group_label}
                  selected={selectedGroups}
                  onChange={handleGroupsChanged}
                  counts={route.name === 'search' && route.mode === 'keyword'
                    ? searchInfo?.keyword?.groups
                    : undefined}
                />
                {route.name === 'search' && collection?.catalog_search && (
                  <ModeToggle mode={route.mode} onChange={handleModeChanged} />
                )}
              </div>
            </div>
          </div>
        )}

        {route.name === 'home' && (
          <>
            <ExampleQueries
              queries={collection?.example_queries}
              groups={selectedGroups}
            />
            <section className="wall">
              <div className="wall-heading">
                <h2>Browse the collection</h2>
                <p>A random selection. Select any image to see it larger and find similar ones.</p>
              </div>
              <ImageGrid items={wall} groupLabels={groupLabels} />
              {wallFailed && (
                <div className="wall-more">
                  <p>The images could not be loaded.</p>
                  <button type="button" onClick={extendWall} disabled={wallIsLoading}>
                    Try again
                  </button>
                </div>
              )}
              {wallHasMore && !wallFailed && (
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
            groupLabels={groupLabels}
            notice={route.name === 'search' && searchInfo && !isLoading ? (
              <SearchNotice
                search={searchInfo}
                query={route.query}
                groups={selectedGroups}
                mode={route.mode}
                exact={route.exact}
                results={results}
                groupLabels={groupLabels}
                groupLabel={collection?.group_label}
              />
            ) : null}
          />
        )}

        {route.name === 'item' && (
          <ItemDetail id={route.id} collection={collection} canGoBack={canGoBack} />
        )}
      </main>

      <SiteFooter collection={collection} />
    </div>
  );
}

export default App;
