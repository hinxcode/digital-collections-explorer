import React, { useState, useCallback, useRef, useEffect } from 'react';
import SearchBar from './components/SearchBar';
import Lightbox from './components/Lightbox';
import SearchResults from './components/SearchResults';
import { searchByText, searchByImage, getEmbeddingStats, getIiifInfo } from './services/api';
import './App.css';

function App() {
  const [maps, setMaps] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const searchInputRef = useRef(null);
  const [selectedMap, setSelectedMap] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [searchMode, setSearchMode] = useState('text'); // 'text' or 'image'
  const [embeddingCount, setEmbeddingCount] = useState(null);
  const resultsPerPage = 50;

  useEffect(() => {
    const fetchEmbeddingStats = async () => {
      try {
        const stats = await getEmbeddingStats();
        setEmbeddingCount(stats.count);
      } catch (error) {
        console.error('Failed to load embedding stats:', error);
      }
    };

    fetchEmbeddingStats();
  }, []);

  const formatItemsForGallery = (results) => {
    return results.map(result => ({
      src: result.metadata.paths.thumbnail,
      width: 200,
      height: 150,
      alt: result.file_name,
      originalData: result
    }));
  };

  const handleSearchByText = useCallback(async (query) => {
    if (!query.trim()) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const results = await searchByText(query, resultsPerPage, currentPage);
      setMaps(formatItemsForGallery(results));
      setHasMore(results.length >= resultsPerPage);
    } catch (error) {
      console.error('Error performing search:', error);
      setError('Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [resultsPerPage, currentPage]);

  const handleSearchByImage = useCallback(async (image) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const results = await searchByImage(image, resultsPerPage, currentPage);
      setMaps(formatItemsForGallery(results));
      setHasMore(results.length >= resultsPerPage);
    } catch (error) {
      console.error('Error performing search:', error);
      setError('Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [resultsPerPage, currentPage]);

  useEffect(() => {
    if (searchMode === 'text' && searchQuery) {
      handleSearchByText(searchQuery);
    } else if (searchMode === 'image' && uploadedImage) {
      handleSearchByImage(uploadedImage);
    }
  }, [currentPage, searchMode, searchQuery, uploadedImage, handleSearchByText, handleSearchByImage]);

  const handleLightboxOpened = useCallback(async (selectedMap) => {
    try {
      const iiifInfo = await getIiifInfo(selectedMap.originalData.metadata.iiif_id);

      setSelectedMap({
        ...selectedMap.originalData,
        iiifInfo: iiifInfo
      });
    } catch (error) {
      console.error("Failed to get IIIF info:", error);
      setError('Failed to get IIIF info from Library of Congress\'s API. Please try again.');
    }
  }, [setSelectedMap]);

  const handleLightboxClosed = useCallback(() => {
    setSelectedMap(null);
  }, [setSelectedMap]);

  const handleSearchModeChanged = useCallback((mode) => {
    setSearchMode(mode);
    setCurrentPage(1);
    setMaps([]);
    setHasMore(false);

    if (mode === 'text') {
      setUploadedImage(null);
    } else {
      setSearchQuery('');
    }
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Historical Maps Explorer</h1>
        <p>Explore maps using natural language search</p>
      </header>
      <main className="App-main">
        <div className="search-controls">
          <SearchBar
            inputRef={searchInputRef}
            searchMode={searchMode}
            setSearchMode={handleSearchModeChanged}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            uploadedImage={uploadedImage}
            setUploadedImage={setUploadedImage}
            onSearchByText={handleSearchByText}
            onSearchByImage={handleSearchByImage}
          />
        </div>
        <SearchResults 
          items={maps}
          isLoading={isLoading}
          error={error}
          onClick={handleLightboxOpened}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          hasMore={hasMore}
        />
        {
          maps.length === 0 && embeddingCount !== null && (
            <div className="welcome-message">
              <p>
                Enter a search term or upload a similar image to discover matches
                from our collection of {embeddingCount.toLocaleString()} maps.
              </p>
            </div>
          )
        }
      </main>
      <Lightbox
        isVisible={!!selectedMap}
        data={selectedMap}
        onBack={handleLightboxClosed}
      />
    </div>
  );
}

export default App;
