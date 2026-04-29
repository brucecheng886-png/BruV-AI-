-- ==========================================================
-- BruV AI Knowledge Base - Initial Database Schema
-- Generated from backup_2026_04_25.sql (schema-only, no data)
-- ==========================================================

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13 (Debian 16.13-1.pgdg13+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_skills; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.agent_skills (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    page_key character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    user_prompt text DEFAULT ''::text NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.agent_skills OWNER TO ai_kb_user;

--
-- Name: chunks; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.chunks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    doc_id uuid NOT NULL,
    content text NOT NULL,
    chunk_index integer NOT NULL,
    vector_id text,
    window_context text,
    page_number integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.chunks OWNER TO ai_kb_user;

--
-- Name: conversations; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.conversations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid,
    title text DEFAULT '?啣?閰?::text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    kb_scope_id uuid,
    doc_scope_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    tag_scope_ids jsonb DEFAULT '[]'::jsonb,
    agent_type character varying(20) DEFAULT 'chat'::character varying,
    agent_meta jsonb DEFAULT '{}'::jsonb,
    summary text,
    summarized_up_to uuid,
    summary_updated_at timestamp with time zone
);


ALTER TABLE public.conversations OWNER TO ai_kb_user;

--
-- Name: crawl_batches; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.crawl_batches (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    batch_name text,
    total integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.crawl_batches OWNER TO ai_kb_user;

--
-- Name: document_knowledge_bases; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.document_knowledge_bases (
    doc_id uuid NOT NULL,
    kb_id uuid NOT NULL,
    score double precision,
    source character varying(20) DEFAULT 'auto'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.document_knowledge_bases OWNER TO ai_kb_user;

--
-- Name: document_tags; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.document_tags (
    doc_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    confidence double precision,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.document_tags OWNER TO ai_kb_user;

--
-- Name: documents; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.documents (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    title text NOT NULL,
    source text,
    file_path text,
    file_type text,
    status text DEFAULT 'pending'::text NOT NULL,
    error_message text,
    chunk_count integer DEFAULT 0,
    custom_fields jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    knowledge_base_id uuid,
    url_fingerprint text,
    batch_id uuid,
    suggested_kb_id uuid,
    suggested_kb_name text,
    suggested_tags jsonb DEFAULT '[]'::jsonb,
    cover_image_url text,
    deleted_at timestamp with time zone
);


ALTER TABLE public.documents OWNER TO ai_kb_user;

--
-- Name: knowledge_bases; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.knowledge_bases (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    color character varying(20) DEFAULT '#2563eb'::character varying,
    icon character varying(50) DEFAULT '??'::character varying,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    embedding_model character varying,
    embedding_provider character varying,
    chunk_size integer,
    chunk_overlap integer,
    language character varying DEFAULT 'auto'::character varying,
    rerank_enabled boolean,
    default_top_k integer
);


ALTER TABLE public.knowledge_bases OWNER TO ai_kb_user;

--
-- Name: llm_models; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.llm_models (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name text NOT NULL,
    family text,
    developer text,
    params_b double precision,
    context_length integer,
    license text,
    release_date date,
    tags text[] DEFAULT '{}'::text[],
    benchmarks jsonb DEFAULT '{}'::jsonb,
    quantizations jsonb DEFAULT '{}'::jsonb,
    ollama_id text,
    hf_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    model_type character varying(20) DEFAULT 'chat'::character varying,
    max_tokens integer,
    vision_support boolean DEFAULT false,
    provider character varying(30),
    base_url character varying(256),
    api_key text
);


ALTER TABLE public.llm_models OWNER TO ai_kb_user;

--
-- Name: messages; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    conv_id uuid NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    sources jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.messages OWNER TO ai_kb_user;

--
-- Name: notion_sync_log; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.notion_sync_log (
    page_id text NOT NULL,
    last_edited_time timestamp with time zone NOT NULL,
    doc_id uuid,
    synced_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.notion_sync_log OWNER TO ai_kb_user;

--
-- Name: ontology_blocklist; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.ontology_blocklist (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name text NOT NULL,
    entity_type text NOT NULL,
    blocked_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ontology_blocklist OWNER TO ai_kb_user;

--
-- Name: ontology_review_queue; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.ontology_review_queue (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    entity_name text NOT NULL,
    entity_type text NOT NULL,
    action text NOT NULL,
    proposed_data jsonb DEFAULT '{}'::jsonb,
    source_doc_id uuid,
    status text DEFAULT 'pending'::text NOT NULL,
    reviewed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ontology_review_queue OWNER TO ai_kb_user;

--
-- Name: plugins; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.plugins (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name text NOT NULL,
    description text,
    input_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    endpoint text NOT NULL,
    auth_header text,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    plugin_type text DEFAULT 'webhook'::text NOT NULL,
    builtin_key text,
    plugin_config jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE public.plugins OWNER TO ai_kb_user;

--
-- Name: prompt_templates; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.prompt_templates (
    template_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    category text NOT NULL,
    title text NOT NULL,
    template text NOT NULL,
    required_vars jsonb DEFAULT '[]'::jsonb NOT NULL,
    optional_vars jsonb DEFAULT '[]'::jsonb NOT NULL,
    example_triggers jsonb DEFAULT '[]'::jsonb NOT NULL,
    pit_warnings jsonb DEFAULT '[]'::jsonb NOT NULL,
    usage_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.prompt_templates OWNER TO ai_kb_user;

--
-- Name: protein_interactions; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.protein_interactions (
    id integer NOT NULL,
    protein_a text NOT NULL,
    protein_b text NOT NULL,
    score double precision NOT NULL,
    network text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.protein_interactions OWNER TO ai_kb_user;

--
-- Name: protein_interactions_id_seq; Type: SEQUENCE; Schema: public; Owner: ai_kb_user
--

CREATE SEQUENCE public.protein_interactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.protein_interactions_id_seq OWNER TO ai_kb_user;

--
-- Name: protein_interactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ai_kb_user
--

ALTER SEQUENCE public.protein_interactions_id_seq OWNED BY public.protein_interactions.id;


--
-- Name: proteins; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.proteins (
    symbol text NOT NULL,
    genecards_url text
);


ALTER TABLE public.proteins OWNER TO ai_kb_user;

--
-- Name: saga_log; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.saga_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    operation text NOT NULL,
    resource_id text NOT NULL,
    completed_steps jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text DEFAULT 'in_progress'::text NOT NULL,
    error_detail text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone
);


ALTER TABLE public.saga_log OWNER TO ai_kb_user;

--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.system_settings (
    key character varying(100) NOT NULL,
    value text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.system_settings OWNER TO ai_kb_user;

--
-- Name: tags; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.tags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(100) NOT NULL,
    slug character varying(100) NOT NULL,
    color character varying(20) DEFAULT '#409eff'::character varying,
    description text,
    parent_id uuid,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.tags OWNER TO ai_kb_user;

--
-- Name: users; Type: TABLE; Schema: public; Owner: ai_kb_user
--

CREATE TABLE public.users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email text NOT NULL,
    password text NOT NULL,
    role text DEFAULT 'user'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.users OWNER TO ai_kb_user;

--
-- Name: protein_interactions id; Type: DEFAULT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.protein_interactions ALTER COLUMN id SET DEFAULT nextval('public.protein_interactions_id_seq'::regclass);


--
-- Data for Name: agent_skills; Type: TABLE DATA; Schema: public; Owner: ai_kb_user
--


-- ── Indexes & Constraints ─────────────────────────────────────

-- Name: agent_skills agent_skills_page_key_key; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.agent_skills
    ADD CONSTRAINT agent_skills_page_key_key UNIQUE (page_key);


--
-- Name: agent_skills agent_skills_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.agent_skills
    ADD CONSTRAINT agent_skills_pkey PRIMARY KEY (id);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: crawl_batches crawl_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.crawl_batches
    ADD CONSTRAINT crawl_batches_pkey PRIMARY KEY (id);


--
-- Name: document_knowledge_bases document_knowledge_bases_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_knowledge_bases
    ADD CONSTRAINT document_knowledge_bases_pkey PRIMARY KEY (doc_id, kb_id);


--
-- Name: document_tags document_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_tags
    ADD CONSTRAINT document_tags_pkey PRIMARY KEY (doc_id, tag_id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: knowledge_bases knowledge_bases_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_pkey PRIMARY KEY (id);


--
-- Name: llm_models llm_models_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT llm_models_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: notion_sync_log notion_sync_log_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.notion_sync_log
    ADD CONSTRAINT notion_sync_log_pkey PRIMARY KEY (page_id);


--
-- Name: ontology_blocklist ontology_blocklist_name_entity_type_key; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.ontology_blocklist
    ADD CONSTRAINT ontology_blocklist_name_entity_type_key UNIQUE (name, entity_type);


--
-- Name: ontology_blocklist ontology_blocklist_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.ontology_blocklist
    ADD CONSTRAINT ontology_blocklist_pkey PRIMARY KEY (id);


--
-- Name: ontology_review_queue ontology_review_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.ontology_review_queue
    ADD CONSTRAINT ontology_review_queue_pkey PRIMARY KEY (id);


--
-- Name: plugins plugins_name_key; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.plugins
    ADD CONSTRAINT plugins_name_key UNIQUE (name);


--
-- Name: plugins plugins_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.plugins
    ADD CONSTRAINT plugins_pkey PRIMARY KEY (id);


--
-- Name: prompt_templates prompt_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.prompt_templates
    ADD CONSTRAINT prompt_templates_pkey PRIMARY KEY (template_id);


--
-- Name: protein_interactions protein_interactions_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.protein_interactions
    ADD CONSTRAINT protein_interactions_pkey PRIMARY KEY (id);


--
-- Name: proteins proteins_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.proteins
    ADD CONSTRAINT proteins_pkey PRIMARY KEY (symbol);


--
-- Name: saga_log saga_log_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.saga_log
    ADD CONSTRAINT saga_log_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key);


--
-- Name: tags tags_name_key; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_name_key UNIQUE (name);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: tags tags_slug_key; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_slug_key UNIQUE (slug);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_chunks_doc_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_chunks_doc_id ON public.chunks USING btree (doc_id);


--
-- Name: idx_chunks_vector_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_chunks_vector_id ON public.chunks USING btree (vector_id);


--
-- Name: idx_dkb_kb_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_dkb_kb_id ON public.document_knowledge_bases USING btree (kb_id);


--
-- Name: idx_document_tags_tag_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_document_tags_tag_id ON public.document_tags USING btree (tag_id);


--
-- Name: idx_documents_batch_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_documents_batch_id ON public.documents USING btree (batch_id);


--
-- Name: idx_documents_created; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_documents_created ON public.documents USING btree (created_at DESC);


--
-- Name: idx_documents_custom; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_documents_custom ON public.documents USING gin (custom_fields);


--
-- Name: idx_documents_status; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_documents_status ON public.documents USING btree (status);


--
-- Name: idx_documents_url_fp; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE UNIQUE INDEX idx_documents_url_fp ON public.documents USING btree (url_fingerprint) WHERE (url_fingerprint IS NOT NULL);


--
-- Name: idx_messages_conv_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_messages_conv_id ON public.messages USING btree (conv_id);


--
-- Name: idx_messages_created; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_messages_created ON public.messages USING btree (created_at);


--
-- Name: idx_orq_entity_uniq; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE UNIQUE INDEX idx_orq_entity_uniq ON public.ontology_review_queue USING btree (entity_name, entity_type) WHERE (status = 'pending'::text);


--
-- Name: idx_pi_network; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_pi_network ON public.protein_interactions USING btree (network);


--
-- Name: idx_pi_pa; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_pi_pa ON public.protein_interactions USING btree (protein_a);


--
-- Name: idx_pi_pb; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_pi_pb ON public.protein_interactions USING btree (protein_b);


--
-- Name: idx_pi_uniq; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE UNIQUE INDEX idx_pi_uniq ON public.protein_interactions USING btree (protein_a, protein_b, network);


--
-- Name: idx_prompt_templates_category; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_prompt_templates_category ON public.prompt_templates USING btree (category);


--
-- Name: idx_saga_log_resource; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_saga_log_resource ON public.saga_log USING btree (resource_id);


--
-- Name: idx_saga_log_status; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_saga_log_status ON public.saga_log USING btree (status);


--
-- Name: idx_tags_parent_id; Type: INDEX; Schema: public; Owner: ai_kb_user
--

CREATE INDEX idx_tags_parent_id ON public.tags USING btree (parent_id);


--
-- Name: chunks chunks_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_kb_scope_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_kb_scope_id_fkey FOREIGN KEY (kb_scope_id) REFERENCES public.knowledge_bases(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_summarized_up_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_summarized_up_to_fkey FOREIGN KEY (summarized_up_to) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: document_knowledge_bases document_knowledge_bases_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_knowledge_bases
    ADD CONSTRAINT document_knowledge_bases_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_knowledge_bases document_knowledge_bases_kb_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_knowledge_bases
    ADD CONSTRAINT document_knowledge_bases_kb_id_fkey FOREIGN KEY (kb_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE;


--
-- Name: document_tags document_tags_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_tags
    ADD CONSTRAINT document_tags_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: document_tags document_tags_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_tags
    ADD CONSTRAINT document_tags_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_tags document_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.document_tags
    ADD CONSTRAINT document_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id) ON DELETE CASCADE;


--
-- Name: documents documents_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.crawl_batches(id);


--
-- Name: documents documents_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: documents documents_knowledge_base_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE SET NULL;


--
-- Name: documents documents_suggested_kb_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_suggested_kb_id_fkey FOREIGN KEY (suggested_kb_id) REFERENCES public.knowledge_bases(id) ON DELETE SET NULL;


--
-- Name: knowledge_bases knowledge_bases_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: messages messages_conv_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conv_id_fkey FOREIGN KEY (conv_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: notion_sync_log notion_sync_log_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.notion_sync_log
    ADD CONSTRAINT notion_sync_log_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: ontology_blocklist ontology_blocklist_blocked_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.ontology_blocklist
    ADD CONSTRAINT ontology_blocklist_blocked_by_fkey FOREIGN KEY (blocked_by) REFERENCES public.users(id);


--
-- Name: ontology_review_queue ontology_review_queue_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.ontology_review_queue
    ADD CONSTRAINT ontology_review_queue_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: ontology_review_queue ontology_review_queue_source_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.ontology_review_queue
    ADD CONSTRAINT ontology_review_queue_source_doc_id_fkey FOREIGN KEY (source_doc_id) REFERENCES public.documents(id);


--
-- Name: tags tags_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: tags tags_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ai_kb_user
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.tags(id) ON DELETE SET NULL;


--
