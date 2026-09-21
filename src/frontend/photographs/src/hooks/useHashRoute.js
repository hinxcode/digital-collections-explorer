import { useCallback, useEffect, useState } from 'react';

const parse = (hash) => {
  const [path, queryString = ''] = hash.replace(/^#/, '').split('?');
  const params = new URLSearchParams(queryString);
  const segments = path.split('/').filter(Boolean);

  if (segments[0] === 'item' && segments[1]) {
    return { name: 'item', id: decodeURIComponent(segments[1]) };
  }
  if (segments[0] === 'search' && params.get('q')) {
    return { name: 'search', query: params.get('q'), page: Number(params.get('page')) || 1 };
  }
  if (segments[0] === 'image-search') {
    return { name: 'image-search', page: Number(params.get('page')) || 1 };
  }
  return { name: 'home' };
};

export const itemHref = (id) => `#/item/${encodeURIComponent(id)}`;

export const searchHref = (query, page = 1) => {
  const params = new URLSearchParams({ q: query });
  if (page > 1) {
    params.set('page', page);
  }
  return `#/search?${params.toString()}`;
};

export const useHashRoute = () => {
  const [route, setRoute] = useState(() => parse(window.location.hash));

  useEffect(() => {
    const onHashChange = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = useCallback((hash) => {
    window.location.hash = hash;
  }, []);

  return [route, navigate];
};
