# TODO: NOC Agent AI - Remaining Tasks

## 🟡 Medium Priority Issues

### 1. MMR Testing and Documentation
**Status**: 🟡 PENDING  
**Impact**: MMR is implemented but not fully tested or documented  
**Location**: `retrieval/hybrid_search.py`, `README.md`

**Tasks**:
- [ ] Test MMR vs RRF performance and result quality
- [ ] Document when to use MMR vs RRF in README.md
- [ ] Add examples of MMR configuration

---

### 2. Integration Tests for Service/Component Filtering
**Status**: 🟡 Medium  
**Tasks**:
- [ ] Test triage with mismatched service/component
- [ ] Test resolution with mismatched service/component
- [ ] Test with NULL service/component values
- [ ] Test with standardized vs non-standardized data
- [ ] Verify confidence levels match expected ranges
- [ ] Verify policy bands work correctly with new confidence levels

---

### 3. Document Service/Component Standardization
**Status**: 🟡 Medium  
**Tasks**:
- [ ] Document service/component naming conventions
- [ ] Create mapping table documentation
- [ ] Add examples of correct vs incorrect values
- [ ] Document ingestion process for new data sources

---

## 🟢 Low Priority / Enhancements

### 4. Embedding Caching
**Status**: 🟢 Low  
**Impact**: Redundant API calls, slower ingestion  
**Location**: `ingestion/embeddings.py`

**Problem**:
- Same text may be embedded multiple times
- No caching of embeddings
- Wastes API quota and time

**Tasks**:
- [ ] Add embedding cache (in-memory or Redis)
- [ ] Cache key: hash of (text, model)
- [ ] Add cache invalidation strategy
- [ ] Monitor cache hit rate

**Files to Modify**:
- `ingestion/embeddings.py` (add caching layer)

---

### 5. Performance Tests for Retrieval
**Status**: 🟢 Low  
**Tasks**:
- [ ] Benchmark retrieval performance with large datasets
- [ ] Test RRF vs MMR performance
- [ ] Measure embedding API call latency
- [ ] Test concurrent retrieval requests

---

### 6. Document Retrieval Configuration
**Status**: 🟢 Low  
**Tasks**:
- [ ] Document RRF parameters
- [ ] Document MMR parameters
- [ ] Document service/component filtering behavior
- [ ] Add troubleshooting guide for retrieval issues

---

## 💡 Long-term Enhancements

### 7. Auto-updating Technical Terms Dictionary
**Status**: 🔵 Future  
**Problem**: Current `technical_terms.json` is static and requires manual updates  
**Solution**: Pattern-based learning from ingested historical data:
- Extract abbreviation patterns (e.g., "DB" → "Database" from context)
- Extract synonym patterns (e.g., "job" and "task" used interchangeably)
- Extract normalization patterns (e.g., "DB", "db", "Database" all refer to same concept)
- Update `technical_terms.json` automatically based on frequency and confidence
- Use statistical analysis, not LLM inference
- Require minimum frequency threshold before adding new mappings
- Human review/approval workflow for new mappings

**Expected Impact**: Self-improving system that adapts to domain-specific terminology

**Tasks**:
- [ ] Add pattern extraction during ingestion (abbreviation detection, synonym co-occurrence)
- [ ] Implement frequency-based confidence scoring
- [ ] Add auto-update mechanism for `technical_terms.json`
- [ ] Add human review workflow for new mappings
- [ ] Test with historical data to validate learning

---

### 8. LLM-based Query Rewriting
**Status**: 🔵 Future  
**Description**: Use LLM to rewrite queries for better retrieval
- Extract intent and expand queries semantically
- Higher cost but potentially better results

---

### 9. Embedding Fine-tuning
**Status**: 🔵 Future  
**Description**: Fine-tune embeddings on domain-specific data
- Better semantic understanding of NOC terminology
- Requires significant data and compute

---

### 10. Hybrid Retrieval with Reranking
**Status**: 🔵 Future  
**Description**: Use cross-encoder for reranking
- More accurate but slower
- Can be used as optional enhancement

---

## 🎯 Priority Summary

**Medium Priority**:
1. 🟡 MMR Testing and Documentation (#1)
2. 🟡 Integration Tests for Service/Component Filtering (#2)
3. 🟡 Document Service/Component Standardization (#3)

**Low Priority**:
4. 🟢 Embedding Caching (#4)
5. 🟢 Performance Tests for Retrieval (#5)
6. 🟢 Document Retrieval Configuration (#6)

**Future Enhancements**:
7. 🔵 Auto-updating Technical Terms Dictionary (#7)
8. 🔵 LLM-based Query Rewriting (#8)
9. 🔵 Embedding Fine-tuning (#9)
10. 🔵 Hybrid Retrieval with Reranking (#10)

---

Last Updated: 2025-01-XX  
Maintainer: NOC Agent AI Team
