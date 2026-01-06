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

### 4. Centralize SQL Query Patterns
**Status**: 🟡 Medium  
**Impact**: Code duplication, maintenance risk, inconsistent scoring logic  
**Location**: `retrieval/hybrid_search.py`, `retrieval/resolution_retrieval.py`

**Problem**:
- 3 complex queries (100+ lines each) with similar patterns
- RRF scoring, soft filter boosts, and parameter building duplicated
- Changes to scoring logic require updates in multiple places
- Risk of bugs from parameter ordering mistakes

**Solution**: Create Query Builder pattern to centralize common components:
- Extract RRF score calculation formulas
- Extract soft filter boost CASE statements (service/component matching)
- Standardize parameter building utilities
- Add query validation helpers

**Tasks**:
- [ ] Create `retrieval/query_builders.py` with shared query components
- [ ] Extract RRF score formula (used in 2 queries)
- [ ] Extract soft filter boost cases (used in all 3 queries)
- [ ] Standardize parameter building logic
- [ ] Refactor `hybrid_search()` query to use builder
- [ ] Refactor `triage_retrieval()` incident signatures query
- [ ] Refactor `triage_retrieval()` runbook metadata query
- [ ] Add unit tests for scoring formulas

**Files to Modify**:
- `retrieval/hybrid_search.py` (refactor queries)
- `retrieval/query_builders.py` (new file - shared components)
- `tests/` (add query builder tests)

---

## 🟢 Low Priority / Enhancements

### 5. Embedding Caching
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

### 6. Performance Tests for Retrieval
**Status**: 🟢 Low  
**Tasks**:
- [ ] Benchmark retrieval performance with large datasets
- [ ] Test RRF vs MMR performance
- [ ] Measure embedding API call latency
- [ ] Test concurrent retrieval requests

---

### 7. Document Retrieval Configuration
**Status**: 🟢 Low  
**Tasks**:
- [ ] Document RRF parameters
- [ ] Document MMR parameters
- [ ] Document service/component filtering behavior
- [ ] Add troubleshooting guide for retrieval issues

---

## 💡 Long-term Enhancements

### 8. Auto-updating Technical Terms Dictionary
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

### 9. LLM-based Query Rewriting
**Status**: 🔵 Future  
**Description**: Use LLM to rewrite queries for better retrieval
- Extract intent and expand queries semantically
- Higher cost but potentially better results

---

### 10. Embedding Fine-tuning
**Status**: 🔵 Future  
**Description**: Fine-tune embeddings on domain-specific data
- Better semantic understanding of NOC terminology
- Requires significant data and compute

---

### 11. Hybrid Retrieval with Reranking
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
4. 🟡 Centralize SQL Query Patterns (#4)

**Low Priority**:
5. 🟢 Embedding Caching (#5)
6. 🟢 Performance Tests for Retrieval (#6)
7. 🟢 Document Retrieval Configuration (#7)

**Future Enhancements**:
8. 🔵 Auto-updating Technical Terms Dictionary (#8)
9. 🔵 LLM-based Query Rewriting (#9)
10. 🔵 Embedding Fine-tuning (#10)
11. 🔵 Hybrid Retrieval with Reranking (#11)

---

Last Updated: 2025-01-XX  
Maintainer: NOC Agent AI Team
