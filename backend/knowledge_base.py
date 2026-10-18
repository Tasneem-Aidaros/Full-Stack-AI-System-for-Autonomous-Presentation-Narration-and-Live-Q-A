class KnowledgeBase:
 
    def __init__(self):
 
        self.slides = []
 
    def build(self, slides, scripts):
 
        self.slides = []
 
        for i, slide in enumerate(slides):
 
            self.slides.append({
 
                "number": i + 1,
 
                "title": slide["text"].split("\n")[0],
 
                "text": slide["text"],
 
                "script": self._script_text(scripts.get(i + 1, ""))
            })
 
    def all_slides(self):
 
        return self.slides
 
    def search(self, question):
 
        question = question.lower()
 
        results = []
 
        words = question.split()
 
        for slide in self.slides:
 
            score = 0
 
            content = (
                slide["title"] +
                " " +
                slide["text"] +
                " " +
                slide["script"]
            ).lower()
 
            for word in words:
 
                if word in content:
 
                    score += 1
 
            results.append((score, slide))
 
        results.sort(reverse=True, key=lambda x: x[0])
 
        return [slide for score, slide in results[:3]]
 
    # -------------------------------------------------
    # Scripts can arrive either as a plain string
    # (e.g. from explain_slide) or as a list of
    # sentences (e.g. from generate_presentation_scripts,
    # which splits scripts into sentences). Normalize
    # either shape into a single searchable string.
    # -------------------------------------------------
    @staticmethod
    def _script_text(script):
 
        if isinstance(script, list):
            return " ".join(script)
 
        if script is None:
            return ""
 
        return str(script)
 
 
knowledge = KnowledgeBase()
 
