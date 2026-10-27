"""Stub frappe.model.document.Document — controller của app chỉ cần kế thừa được."""
class Document(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            return None
