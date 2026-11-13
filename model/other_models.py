# -*- coding: utf-8 -*-
"""Any token-classification model from the Hugging Face hub, run the way PIIMB runs every model: the network alone,
the most likely class of each token, and whatever is not "O" counts as masked. It lets benchmark.py measure other
PII detectors with exactly the same code and the same texts as ours:

  python benchmark.py <hub id or folder> --mode other [--save]

Only weights in safetensors format are loaded, and no code from the model repository is executed.
"""
import os


class Other:
    def __init__(self, name, device=None, window=512, stride=96, batch=32):
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(name)
        self.mod = AutoModelForTokenClassification.from_pretrained(name, use_safetensors=True).to(self.device).eval()
        labels = {int(i): str(label) for i, label in self.mod.config.id2label.items()}
        self.outside = [i for i, label in labels.items() if label.upper() in ("O", "OUTSIDE", "NONE")]
        if not self.outside:
            raise SystemExit(f"{name}: no label \"O\" among {sorted(set(labels.values()))[:12]}: cannot tell what it leaves in clear")
        self.labels = labels
        limit = getattr(self.mod.config, "max_position_embeddings", None) or 512
        self.window, self.stride, self.batch = min(window, limit - 2), stride, batch
        self.name = os.path.basename(str(name).rstrip("/\\")) if os.path.isdir(str(name)) else str(name)

    def molti(self, texts, completo=False):
        """[[start, end, label], ...] for every text. `completo` is accepted and ignored: there is nothing but the network."""
        torch, out = self.torch, [None] * len(texts)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))        # similar lengths together: less padding
        outside = torch.tensor(self.outside, device=self.device)
        for k in range(0, len(order), 256):
            part = order[k:k + 256]
            enc = self.tok([texts[i] or " " for i in part], return_offsets_mapping=True, truncation=True, max_length=self.window,
                           stride=self.stride, return_overflowing_tokens=True, padding=True, return_tensors="pt")
            offsets, owner = enc.pop("offset_mapping").tolist(), enc.pop("overflow_to_sample_mapping").tolist()
            enc = {key: value for key, value in enc.items() if key in ("input_ids", "attention_mask")}
            classes = []
            with torch.no_grad(), torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
                for b in range(0, len(owner), self.batch):
                    logits = self.mod(**{key: value[b:b + self.batch].to(self.device) for key, value in enc.items()}).logits
                    best = logits.argmax(-1)
                    classes.append(torch.where(torch.isin(best, outside), torch.full_like(best, -1), best).cpu())
            classes = torch.cat(classes).tolist()
            lengths = enc["attention_mask"].sum(1).tolist()
            found = {i: {} for i in part}        # per text: character -> class, from the window where the token is most central
            for w, sample in enumerate(owner):
                text_index, n = part[sample], lengths[w]
                real = [t for t in range(len(offsets[w])) if offsets[w][t][1] > offsets[w][t][0]]
                for position, t in enumerate(real):
                    centre = min(position, len(real) - 1 - position)
                    s, e = offsets[w][t]
                    seen = found[text_index].get((s, e))
                    if seen is None or centre > seen[0]:
                        found[text_index][(s, e)] = (centre, classes[w][t])
            for i in part:
                out[i] = self._spans(texts[i] or " ", sorted((s, e, c) for (s, e), (_, c) in found[i].items()))
        return out

    def _spans(self, text, tokens):
        """Consecutive masked tokens become one span (the space between two words of a name is part of the name);
        the blanks that some tokenizers attach to a token are left out."""
        spans, current, previous_masked = [], None, False
        for s, e, c in tokens:
            if c < 0:
                current, previous_masked = None, False
                continue
            if current is not None and previous_masked and not text[current[1]:s].strip():
                current[1] = max(current[1], e)
            else:
                current = [s, e, self.labels[c].split("-", 1)[-1]]
                spans.append(current)
            previous_masked = True
        out = []
        for s, e, label in spans:
            while s < e and text[s].isspace():
                s += 1
            while e > s and text[e - 1].isspace():
                e -= 1
            if e > s:
                out.append([s, e, label])
        return out
