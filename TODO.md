# TODO: NOC Agent AI - Remaining Tasks

## 🟡 Medium Priority Issues

### 1. ✅ Remove Hardcoded Step Type and Risk Level Logic (COMPLETED)
**Status**: ✅ COMPLETED  
**Impact**: Step type detection, risk level assessment, and step ordering are now config-driven  
**Location**: `ai_service/step_transformation.py`, `ai_service/ranking.py`, `ai_service/policy.py`, `config/step_classification.json`

**Completed**:
- ✅ Created `config/step_classification.json` with:
  - Step type definitions and priority order
  - Documentation phrase patterns
  - Risk level definitions and keywords
  - Dangerous action keywords
  - Modification keywords
  - Condition text exclusions
- ✅ Refactored `step_transformation.py` to use config
- ✅ Refactored `ranking.py` to use config
- ✅ Refactored `policy.py` to use config
- ✅ All hardcoded step type and risk level logic removed

**Benefits**:
- Zero hardcoding: all step classification logic comes from config
- Fully extensible: add new step types or risk keywords without code changes
- Maintainable: centralized configuration
- Consistent: same classification logic used everywhere

---

### 2. ✅ Remove Hardcoded Problem Keyword Detection (COMPLETED)
**Status**: ✅ COMPLETED  
**Impact**: Problem keyword extraction is now config-driven  
**Location**: `ai_service/agents/resolution_agent.py`, `config/problem_keywords.json`

**Completed**:
- ✅ Created `config/problem_keywords.json` with:
  - Corrective action keywords
  - Step type filters
  - Problem keyword groups (connection, replication, deadlock, performance, cluster, disk, IO, memory, CPU, network)
- ✅ Refactored `resolution_agent.py` to use config-driven keyword detection
- ✅ All hardcoded problem keyword lists removed

**Benefits**:
- Zero hardcoding: all problem keyword detection comes from config
- Fully extensible: add new problem types or keywords without code changes
- Maintainable: centralized configuration
- Consistent: same keyword detection logic used everywhere

---

### 3. Remove Hardcoded UI Defaults
**Status**: 🟢 LOW PRIORITY  
**Impact**: UI components have hardcoded default values  
**Location**: `ui/src/App.jsx`, `ui/src/components/TicketForm.tsx`

**Hardcoded Values Found**:
- **App.jsx**:
  - Line 9-16: `allowedCategories` array (hardcoded)
  - Line 18-23: `emptyLabels` object with `service: "Database"`, `component: "Alerts"`, `cmdb_ci: "Database-SQL"` (hardcoded)
- **TicketForm.tsx**:
  - Line 20-23: `allowedCategories` array (hardcoded)
  - Line 25-29: `emptyLabels` object with `service: "Database"`, `component: "Database"`, `cmdb_ci: "Database-SQL"` (hardcoded)

**Tasks**:
- [ ] Create API endpoint to fetch UI defaults from config
- [ ] Or create `config/ui_defaults.json` and load in UI
- [ ] Refactor UI components to use config-driven defaults
- [ ] Ensure defaults match backend service/component mappings

---

### 4. MMR Testing and Documentation
**Status**: 🟡 PENDING  
**Impact**: MMR is implemented but not fully tested or documented  
**Location**: `retrieval/hybrid_search.py`, `README.md`

**Tasks**:
- [ ] Test MMR vs RRF performance and result quality
- [ ] Document when to use MMR vs RRF in README.md
- [ ] Add examples of MMR configuration

---

### 5. Integration Tests for Service/Component Filtering
**Status**: 🟡 Medium  
**Tasks**:
- [ ] Test triage with mismatched service/component
- [ ] Test resolution with mismatched service/component
- [ ] Test with NULL service/component values
- [ ] Test with standardized vs non-standardized data
- [ ] Verify confidence levels match expected ranges
- [ ] Verify policy bands work correctly with new confidence levels

---

### 6. Document Service/Component Standardization
**Status**: 🟡 Medium  
**Tasks**:
- [ ] Document service/component naming conventions
- [ ] Create mapping table documentation
- [ ] Add examples of correct vs incorrect values
- [ ] Document ingestion process for new data sources

---

## 🟢 Low Priority / Enhancements

### 1. Embedding Caching
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

### 2. Performance Tests for Retrieval
**Status**: 🟢 Low  
**Tasks**:
- [ ] Benchmark retrieval performance with large datasets
- [ ] Test RRF vs MMR performance
- [ ] Measure embedding API call latency
- [ ] Test concurrent retrieval requests

---

### 3. Document Retrieval Configuration
**Status**: 🟢 Low  
**Tasks**:
- [ ] Document RRF parameters
- [ ] Document MMR parameters
- [ ] Document service/component filtering behavior
- [ ] Add troubleshooting guide for retrieval issues

---

## 💡 Long-term Enhancements

### 1. Auto-updating Technical Terms Dictionary
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

### 2. LLM-based Query Rewriting
**Status**: 🔵 Future  
**Description**: Use LLM to rewrite queries for better retrieval
- Extract intent and expand queries semantically
- Higher cost but potentially better results

---

### 3. Embedding Fine-tuning
**Status**: 🔵 Future  
**Description**: Fine-tune embeddings on domain-specific data
- Better semantic understanding of NOC terminology
- Requires significant data and compute

---

### 4. Hybrid Retrieval with Reranking
**Status**: 🔵 Future  
**Description**: Use cross-encoder for reranking
- More accurate but slower
- Can be used as optional enhancement

---

## 🎯 Priority Summary

**Medium Priority**:
1. ✅ Remove Hardcoded Step Type and Risk Level Logic (#1) - COMPLETED
2. ✅ Remove Hardcoded Problem Keyword Detection (#2) - COMPLETED
3. 🟢 Remove Hardcoded UI Defaults (#3) - LOW PRIORITY
4. 🟡 MMR Testing and Documentation (#4)
5. 🟡 Integration Tests for Service/Component Filtering (#5)
6. 🟡 Document Service/Component Standardization (#6)

**Low Priority**:
1. 🟢 Embedding Caching (#1)
2. 🟢 Performance Tests for Retrieval (#2)
3. 🟢 Document Retrieval Configuration (#3)

**Future Enhancements**:
1. 🔵 Auto-updating Technical Terms Dictionary (#1)
2. 🔵 LLM-based Query Rewriting (#2)
3. 🔵 Embedding Fine-tuning (#3)
4. 🔵 Hybrid Retrieval with Reranking (#4)

---

Last Updated: 2025-01-XX  
Maintainer: NOC Agent AI Team
