export interface PagedListSnapshot<T> {
  items: T[]
  skip: number
  hasMore: boolean
  loading: boolean
}

export interface PagedListLoader<T> {
  refresh(): Promise<PagedListSnapshot<T>>
  loadMore(): Promise<PagedListSnapshot<T>>
  getSnapshot(): PagedListSnapshot<T>
}

export interface PagedListPage<T> {
  items: T[]
  hasMore?: boolean
}

interface PagedListOptions<T> {
  pageSize?: number
  fetchPage(skip: number, limit: number): Promise<T[] | PagedListPage<T>>
  onChange(snapshot: PagedListSnapshot<T>): void
}

/**
 * Reusable skip/limit loader for mini-program list pages.
 * Pages only need to connect refresh/loadMore to their lifecycle hooks.
 */
export function createPagedListLoader<T>(options: PagedListOptions<T>): PagedListLoader<T> {
  const pageSize = options.pageSize ?? 20
  let snapshot: PagedListSnapshot<T> = {
    items: [],
    skip: 0,
    hasMore: true,
    loading: false,
  }

  const update = (next: PagedListSnapshot<T>) => {
    snapshot = next
    options.onChange(snapshot)
  }

  const load = async (append: boolean): Promise<PagedListSnapshot<T>> => {
    if (snapshot.loading || (append && !snapshot.hasMore)) {
      return snapshot
    }

    const skip = append ? snapshot.skip : 0
    update({ ...snapshot, loading: true })

    try {
      const result = await options.fetchPage(skip, pageSize)
      const page = Array.isArray(result) ? result : result.items
      const items = append ? [...snapshot.items, ...page] : page
      update({
        items,
        skip: skip + page.length,
        hasMore: Array.isArray(result)
          ? page.length === pageSize
          : (result.hasMore ?? page.length === pageSize),
        loading: false,
      })
      return snapshot
    } catch (error) {
      update({ ...snapshot, loading: false })
      throw error
    }
  }

  return {
    refresh: () => load(false),
    loadMore: () => load(true),
    getSnapshot: () => snapshot,
  }
}
