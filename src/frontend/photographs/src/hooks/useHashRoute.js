import { useCallback, useEffect, useRef, useState } from 'react';

const groupsFrom = (params) => (params.get('groups') || '').split(',').filter(Boolean);

const parse = (hash) => {
  const [path, queryString = ''] = hash.replace(/^#/, '').split('?');
  const params = new URLSearchParams(queryString);
  const segments = path.split('/').filter(Boolean);

  if (segments[0] === 'item' && segments[1]) {
    return { name: 'item', id: decodeURIComponent(segments[1]) };
  }
  const groups = groupsFrom(params);
  if (segments[0] === 'search' && params.get('q')) {
    return {
      name: 'search', query: params.get('q'), page: Number(params.get('page')) || 1, groups,
    };
  }
  if (segments[0] === 'image-search') {
    return { name: 'image-search', page: Number(params.get('page')) || 1, groups };
  }
  return { name: 'home', groups };
};

const hashFor = (path, params, groups) => {
  if (groups.length > 0) {
    params.set('groups', groups.join(','));
  }
  const query = params.toString().replace(/%2C/gi, ',');
  return query ? `#/${path}?${query}` : `#/${path}`;
};

export const itemHref = (id) => `#/item/${encodeURIComponent(id)}`;

export const homeHref = (groups = []) => hashFor('', new URLSearchParams(), groups);

export const searchHref = (query, page = 1, groups = []) => {
  const params = new URLSearchParams({ q: query });
  if (page > 1) {
    params.set('page', page);
  }
  return hashFor('search', params, groups);
};

export const imageSearchHref = (page = 1, groups = []) => {
  const params = new URLSearchParams();
  if (page > 1) {
    params.set('page', page);
  }
  return hashFor('image-search', params, groups);
};

const HOME = '#/';

const stepsIntoSite = () => window.history.state?.stepsIntoSite;

const rememberStep = (previous) => {
  if (stepsIntoSite() === undefined) {
    const state = { ...window.history.state, stepsIntoSite: previous + 1 };
    window.history.replaceState(state, '', window.location.hash || HOME);
  }
  return stepsIntoSite();
};

const inPageLink = (event) => {
  if (event.defaultPrevented || event.button !== 0) {
    return null;
  }
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return null;
  }
  const link = event.target.closest?.('a[href^="#/"]');
  return link && !link.target ? link.getAttribute('href') : null;
};

export const useHashRoute = () => {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  const [canGoBack, setCanGoBack] = useState(false);
  const current = useRef(0);

  const show = useCallback(() => {
    current.current = rememberStep(current.current);
    setCanGoBack(current.current > 0);
    setRoute(parse(window.location.hash));
    window.scrollTo(0, 0);
  }, []);

  const navigate = useCallback((hash) => {
    if (hash !== window.location.hash) {
      window.history.pushState({ stepsIntoSite: current.current + 1 }, '', hash);
    }
    show();
  }, [show]);

  useEffect(() => {
    current.current = rememberStep(-1);
    setCanGoBack(current.current > 0);

    const onClick = (event) => {
      const hash = inPageLink(event);
      if (hash) {
        event.preventDefault();
        navigate(hash);
      }
    };
    window.addEventListener('popstate', show);
    window.addEventListener('hashchange', show);
    document.addEventListener('click', onClick);
    return () => {
      window.removeEventListener('popstate', show);
      window.removeEventListener('hashchange', show);
      document.removeEventListener('click', onClick);
    };
  }, [navigate, show]);

  return [route, navigate, canGoBack];
};
