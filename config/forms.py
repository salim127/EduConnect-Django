from django import forms


class BootstrapFormMixin:
    """Ajoute les classes Bootstrap à tous les widgets d'un formulaire."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs['class'] = 'form-check-input'
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs['class'] = 'form-select'
            elif not isinstance(w, forms.CheckboxSelectMultiple):
                w.attrs['class'] = 'form-control'
