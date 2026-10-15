class QueryStringMixin:
    """Expose `querystring` (GET sans `page`) pour conserver filtres + pagination."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.copy()
        q.pop('page', None)
        ctx['querystring'] = q.urlencode()
        return ctx
