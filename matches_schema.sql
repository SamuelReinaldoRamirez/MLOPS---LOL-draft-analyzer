--
-- PostgreSQL database dump
--

\restrict axo0Cno2eBwsSb7gzP5DmNagER25NSVA8hmuERYlzjXubTMfXDRXeo4AIq2TOKe

-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: matches; Type: TABLE; Schema: public; Owner: lol_admin
--

CREATE TABLE public.matches (
    match_id text NOT NULL,
    game_creation bigint,
    game_duration integer,
    game_version text,
    queue_id integer DEFAULT 420,
    map_id integer,
    game_mode text,
    game_type text,
    team_100_win smallint,
    team_100_early_surrendered smallint DEFAULT 0,
    team_200_early_surrendered smallint DEFAULT 0,
    collected_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    region text,
    source_elo text
);


ALTER TABLE public.matches OWNER TO lol_admin;

--
-- PostgreSQL database dump complete
--

\unrestrict axo0Cno2eBwsSb7gzP5DmNagER25NSVA8hmuERYlzjXubTMfXDRXeo4AIq2TOKe

