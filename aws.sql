--
-- PostgreSQL database dump
--

-- Dumped from database version 17.5
-- Dumped by pg_dump version 17.5

-- Started on 2025-12-24 02:22:24

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 248 (class 1255 OID 58018)
-- Name: calculate_project_emissions(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_project_emissions(project_id integer) RETURNS TABLE(total_co2e_kg numeric, credits_earned numeric)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(SUM(
            e.asphalt_t * ef_asphalt.co2e_per_unit +
            e.aggregate_t * ef_aggregate.co2e_per_unit +
            e.cement_t * ef_cement.co2e_per_unit +
            e.steel_t * ef_steel.co2e_per_unit +
            e.diesel_l * ef_diesel.co2e_per_unit +
            e.electricity_kwh * ef_electricity.co2e_per_unit +
            e.transport_tkm * ef_transport.co2e_per_unit
        ), 0) AS total_co2e_kg,
        COALESCE(SUM(
            (e.asphalt_t * ef_asphalt.co2e_per_unit +
            e.aggregate_t * ef_aggregate.co2e_per_unit +
            e.cement_t * ef_cement.co2e_per_unit +
            e.steel_t * ef_steel.co2e_per_unit +
            e.diesel_l * ef_diesel.co2e_per_unit +
            e.electricity_kwh * ef_electricity.co2e_per_unit +
            e.transport_tkm * ef_transport.co2e_per_unit) *
            (e.recycled_pct * 0.3 + e.renewable_pct * 0.4) / 100
        ) / 1000, 0) AS credits_earned
    FROM emissions e
    JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
    JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
    JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
    JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
    JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
    JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
    JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
    WHERE e.project_id = calculate_project_emissions.project_id;
END;
$$;


ALTER FUNCTION public.calculate_project_emissions(project_id integer) OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 236 (class 1259 OID 100201)
-- Name: carbon_credit_transactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.carbon_credit_transactions (
    id integer NOT NULL,
    from_user_id integer,
    to_user_id integer,
    quantity numeric(10,2) NOT NULL,
    price_per_credit numeric(10,2),
    total_price numeric(10,2),
    from_project_id integer,
    to_project_id integer,
    listing_id integer,
    transaction_type character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying,
    payment_reference character varying(100),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.carbon_credit_transactions OWNER TO postgres;

--
-- TOC entry 235 (class 1259 OID 100200)
-- Name: carbon_credit_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.carbon_credit_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.carbon_credit_transactions_id_seq OWNER TO postgres;

--
-- TOC entry 5040 (class 0 OID 0)
-- Dependencies: 235
-- Name: carbon_credit_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.carbon_credit_transactions_id_seq OWNED BY public.carbon_credit_transactions.id;


--
-- TOC entry 230 (class 1259 OID 100056)
-- Name: carbon_credits; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.carbon_credits (
    id integer NOT NULL,
    project_id integer NOT NULL,
    user_id integer NOT NULL,
    credits_earned numeric(10,2) DEFAULT 0 NOT NULL,
    credits_used numeric(10,2) DEFAULT 0,
    listed_quantity numeric(10,2) DEFAULT 0,
    credit_value numeric(12,2) DEFAULT 0,
    transaction_type character varying(50) DEFAULT 'ISSUANCE'::character varying,
    status character varying(50) DEFAULT 'available'::character varying,
    issued_at date DEFAULT CURRENT_DATE,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    source character varying(20) DEFAULT 'ISSUANCE'::character varying,
    CONSTRAINT chk_credit_value_positive CHECK ((credit_value >= (0)::numeric)),
    CONSTRAINT chk_credits_earned_positive CHECK ((credits_earned >= (0)::numeric)),
    CONSTRAINT chk_transaction_type CHECK (((transaction_type)::text = ANY ((ARRAY['ISSUANCE'::character varying, 'PURCHASE'::character varying, 'TRANSFER'::character varying])::text[])))
);


ALTER TABLE public.carbon_credits OWNER TO postgres;

--
-- TOC entry 229 (class 1259 OID 100055)
-- Name: carbon_credits_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.carbon_credits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.carbon_credits_id_seq OWNER TO postgres;

--
-- TOC entry 5043 (class 0 OID 0)
-- Dependencies: 229
-- Name: carbon_credits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.carbon_credits_id_seq OWNED BY public.carbon_credits.id;


--
-- TOC entry 234 (class 1259 OID 100104)
-- Name: credit_transactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.credit_transactions (
    id integer NOT NULL,
    listing_id integer,
    buyer_id integer NOT NULL,
    seller_id integer NOT NULL,
    credit_id integer,
    quantity numeric(10,2) NOT NULL,
    total_price numeric(12,2) NOT NULL,
    transaction_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_different_users CHECK ((buyer_id <> seller_id))
);


ALTER TABLE public.credit_transactions OWNER TO postgres;

--
-- TOC entry 233 (class 1259 OID 100103)
-- Name: credit_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.credit_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.credit_transactions_id_seq OWNER TO postgres;

--
-- TOC entry 5046 (class 0 OID 0)
-- Dependencies: 233
-- Name: credit_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.credit_transactions_id_seq OWNED BY public.credit_transactions.id;


--
-- TOC entry 222 (class 1259 OID 99989)
-- Name: emission_factors; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.emission_factors (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    co2e_per_unit numeric(10,4) NOT NULL,
    unit character varying(50) NOT NULL,
    category character varying(100),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.emission_factors OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 99988)
-- Name: emission_factors_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.emission_factors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.emission_factors_id_seq OWNER TO postgres;

--
-- TOC entry 5049 (class 0 OID 0)
-- Dependencies: 221
-- Name: emission_factors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.emission_factors_id_seq OWNED BY public.emission_factors.id;


--
-- TOC entry 226 (class 1259 OID 100015)
-- Name: emissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.emissions (
    id integer NOT NULL,
    project_id integer NOT NULL,
    asphalt_t numeric(10,2) DEFAULT 0,
    aggregate_t numeric(10,2) DEFAULT 0,
    cement_t numeric(10,2) DEFAULT 0,
    steel_t numeric(10,2) DEFAULT 0,
    diesel_l numeric(10,2) DEFAULT 0,
    electricity_kwh numeric(10,2) DEFAULT 0,
    transport_tkm numeric(10,2) DEFAULT 0,
    water_use numeric(10,2) DEFAULT 0,
    waste_t numeric(10,2) DEFAULT 0,
    recycled_pct numeric(5,2) DEFAULT 0,
    renewable_pct numeric(5,2) DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.emissions OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 100014)
-- Name: emissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.emissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.emissions_id_seq OWNER TO postgres;

--
-- TOC entry 5052 (class 0 OID 0)
-- Dependencies: 225
-- Name: emissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.emissions_id_seq OWNED BY public.emissions.id;


--
-- TOC entry 232 (class 1259 OID 100082)
-- Name: marketplace_listings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.marketplace_listings (
    id integer NOT NULL,
    credit_id integer NOT NULL,
    seller_id integer NOT NULL,
    quantity_available numeric(10,2) NOT NULL,
    price_per_credit numeric(10,2) NOT NULL,
    status character varying(50) DEFAULT 'active'::character varying,
    listed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_price_positive CHECK ((price_per_credit > (0)::numeric)),
    CONSTRAINT chk_quantity_positive CHECK ((quantity_available >= (0)::numeric)),
    CONSTRAINT chk_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'sold'::character varying, 'cancelled'::character varying])::text[])))
);


ALTER TABLE public.marketplace_listings OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 100081)
-- Name: marketplace_listings_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.marketplace_listings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.marketplace_listings_id_seq OWNER TO postgres;

--
-- TOC entry 5055 (class 0 OID 0)
-- Dependencies: 231
-- Name: marketplace_listings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.marketplace_listings_id_seq OWNED BY public.marketplace_listings.id;


--
-- TOC entry 224 (class 1259 OID 99999)
-- Name: projects; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.projects (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(200) NOT NULL,
    type character varying(100),
    location character varying(200),
    start_date date,
    end_date date,
    status character varying(50) DEFAULT 'Active'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.projects OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 99998)
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.projects_id_seq OWNER TO postgres;

--
-- TOC entry 5058 (class 0 OID 0)
-- Dependencies: 223
-- Name: projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.projects_id_seq OWNED BY public.projects.id;


--
-- TOC entry 228 (class 1259 OID 100039)
-- Name: recommendations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.recommendations (
    id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(200) NOT NULL,
    description text,
    impact character varying(50),
    cost numeric(10,2),
    category character varying(100),
    display_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.recommendations OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 100038)
-- Name: recommendations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.recommendations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.recommendations_id_seq OWNER TO postgres;

--
-- TOC entry 5061 (class 0 OID 0)
-- Dependencies: 227
-- Name: recommendations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.recommendations_id_seq OWNED BY public.recommendations.id;


--
-- TOC entry 218 (class 1259 OID 57987)
-- Name: reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reports (
    id integer NOT NULL,
    user_id integer,
    project_id integer,
    name character varying(255) NOT NULL,
    file_path text NOT NULL,
    file_size integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.reports OWNER TO postgres;

--
-- TOC entry 217 (class 1259 OID 57986)
-- Name: reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reports_id_seq OWNER TO postgres;

--
-- TOC entry 5064 (class 0 OID 0)
-- Dependencies: 217
-- Name: reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reports_id_seq OWNED BY public.reports.id;


--
-- TOC entry 220 (class 1259 OID 99975)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(150) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    password_hash character varying(255) DEFAULT 'hash'::character varying NOT NULL,
    role character varying(20) DEFAULT 'user'::character varying
);


ALTER TABLE public.users OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 99974)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- TOC entry 5067 (class 0 OID 0)
-- Dependencies: 219
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- TOC entry 4832 (class 2604 OID 100204)
-- Name: carbon_credit_transactions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions ALTER COLUMN id SET DEFAULT nextval('public.carbon_credit_transactions_id_seq'::regclass);


--
-- TOC entry 4817 (class 2604 OID 100059)
-- Name: carbon_credits id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credits ALTER COLUMN id SET DEFAULT nextval('public.carbon_credits_id_seq'::regclass);


--
-- TOC entry 4830 (class 2604 OID 100107)
-- Name: credit_transactions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.credit_transactions ALTER COLUMN id SET DEFAULT nextval('public.credit_transactions_id_seq'::regclass);


--
-- TOC entry 4795 (class 2604 OID 99992)
-- Name: emission_factors id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.emission_factors ALTER COLUMN id SET DEFAULT nextval('public.emission_factors_id_seq'::regclass);


--
-- TOC entry 4800 (class 2604 OID 100018)
-- Name: emissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.emissions ALTER COLUMN id SET DEFAULT nextval('public.emissions_id_seq'::regclass);


--
-- TOC entry 4827 (class 2604 OID 100085)
-- Name: marketplace_listings id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marketplace_listings ALTER COLUMN id SET DEFAULT nextval('public.marketplace_listings_id_seq'::regclass);


--
-- TOC entry 4797 (class 2604 OID 100002)
-- Name: projects id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects ALTER COLUMN id SET DEFAULT nextval('public.projects_id_seq'::regclass);


--
-- TOC entry 4813 (class 2604 OID 100042)
-- Name: recommendations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recommendations ALTER COLUMN id SET DEFAULT nextval('public.recommendations_id_seq'::regclass);


--
-- TOC entry 4788 (class 2604 OID 57990)
-- Name: reports id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reports ALTER COLUMN id SET DEFAULT nextval('public.reports_id_seq'::regclass);


--
-- TOC entry 4791 (class 2604 OID 99978)
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- TOC entry 4870 (class 2606 OID 100209)
-- Name: carbon_credit_transactions carbon_credit_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions
    ADD CONSTRAINT carbon_credit_transactions_pkey PRIMARY KEY (id);


--
-- TOC entry 4864 (class 2606 OID 100070)
-- Name: carbon_credits carbon_credits_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credits
    ADD CONSTRAINT carbon_credits_pkey PRIMARY KEY (id);


--
-- TOC entry 4868 (class 2606 OID 100111)
-- Name: credit_transactions credit_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_pkey PRIMARY KEY (id);


--
-- TOC entry 4854 (class 2606 OID 99997)
-- Name: emission_factors emission_factors_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.emission_factors
    ADD CONSTRAINT emission_factors_name_key UNIQUE (name);


--
-- TOC entry 4856 (class 2606 OID 99995)
-- Name: emission_factors emission_factors_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.emission_factors
    ADD CONSTRAINT emission_factors_pkey PRIMARY KEY (id);


--
-- TOC entry 4860 (class 2606 OID 100032)
-- Name: emissions emissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.emissions
    ADD CONSTRAINT emissions_pkey PRIMARY KEY (id);


--
-- TOC entry 4866 (class 2606 OID 100092)
-- Name: marketplace_listings marketplace_listings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marketplace_listings
    ADD CONSTRAINT marketplace_listings_pkey PRIMARY KEY (id);


--
-- TOC entry 4858 (class 2606 OID 100008)
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- TOC entry 4862 (class 2606 OID 100049)
-- Name: recommendations recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recommendations
    ADD CONSTRAINT recommendations_pkey PRIMARY KEY (id);


--
-- TOC entry 4846 (class 2606 OID 57996)
-- Name: reports reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (id);


--
-- TOC entry 4848 (class 2606 OID 99987)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 4850 (class 2606 OID 99983)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 4852 (class 2606 OID 99985)
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- TOC entry 4843 (class 1259 OID 58012)
-- Name: idx_reports_project_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reports_project_id ON public.reports USING btree (project_id);


--
-- TOC entry 4844 (class 1259 OID 58011)
-- Name: idx_reports_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reports_user_id ON public.reports USING btree (user_id);


--
-- TOC entry 4882 (class 2606 OID 100220)
-- Name: carbon_credit_transactions carbon_credit_transactions_from_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions
    ADD CONSTRAINT carbon_credit_transactions_from_project_id_fkey FOREIGN KEY (from_project_id) REFERENCES public.projects(id);


--
-- TOC entry 4883 (class 2606 OID 100210)
-- Name: carbon_credit_transactions carbon_credit_transactions_from_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions
    ADD CONSTRAINT carbon_credit_transactions_from_user_id_fkey FOREIGN KEY (from_user_id) REFERENCES public.users(id);


--
-- TOC entry 4884 (class 2606 OID 100230)
-- Name: carbon_credit_transactions carbon_credit_transactions_listing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions
    ADD CONSTRAINT carbon_credit_transactions_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES public.marketplace_listings(id);


--
-- TOC entry 4885 (class 2606 OID 100225)
-- Name: carbon_credit_transactions carbon_credit_transactions_to_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions
    ADD CONSTRAINT carbon_credit_transactions_to_project_id_fkey FOREIGN KEY (to_project_id) REFERENCES public.projects(id);


--
-- TOC entry 4886 (class 2606 OID 100215)
-- Name: carbon_credit_transactions carbon_credit_transactions_to_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credit_transactions
    ADD CONSTRAINT carbon_credit_transactions_to_user_id_fkey FOREIGN KEY (to_user_id) REFERENCES public.users(id);


--
-- TOC entry 4874 (class 2606 OID 100071)
-- Name: carbon_credits carbon_credits_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credits
    ADD CONSTRAINT carbon_credits_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- TOC entry 4875 (class 2606 OID 100076)
-- Name: carbon_credits carbon_credits_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.carbon_credits
    ADD CONSTRAINT carbon_credits_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4878 (class 2606 OID 100117)
-- Name: credit_transactions credit_transactions_buyer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_buyer_id_fkey FOREIGN KEY (buyer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4879 (class 2606 OID 100127)
-- Name: credit_transactions credit_transactions_credit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_credit_id_fkey FOREIGN KEY (credit_id) REFERENCES public.carbon_credits(id) ON DELETE SET NULL;


--
-- TOC entry 4880 (class 2606 OID 100112)
-- Name: credit_transactions credit_transactions_listing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES public.marketplace_listings(id) ON DELETE SET NULL;


--
-- TOC entry 4881 (class 2606 OID 100122)
-- Name: credit_transactions credit_transactions_seller_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4872 (class 2606 OID 100033)
-- Name: emissions emissions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.emissions
    ADD CONSTRAINT emissions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- TOC entry 4876 (class 2606 OID 100093)
-- Name: marketplace_listings marketplace_listings_credit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marketplace_listings
    ADD CONSTRAINT marketplace_listings_credit_id_fkey FOREIGN KEY (credit_id) REFERENCES public.carbon_credits(id) ON DELETE CASCADE;


--
-- TOC entry 4877 (class 2606 OID 100098)
-- Name: marketplace_listings marketplace_listings_seller_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marketplace_listings
    ADD CONSTRAINT marketplace_listings_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4871 (class 2606 OID 100009)
-- Name: projects projects_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4873 (class 2606 OID 100050)
-- Name: recommendations recommendations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recommendations
    ADD CONSTRAINT recommendations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- TOC entry 5032 (class 3256 OID 100242)
-- Name: users user_owns_profile; Type: POLICY; Schema: public; Owner: postgres
--

CREATE POLICY user_owns_profile ON public.users USING ((id = (current_setting('app.user_id'::text, true))::integer));


--
-- TOC entry 5038 (class 0 OID 0)
-- Dependencies: 5
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT USAGE ON SCHEMA public TO app_user;


--
-- TOC entry 5039 (class 0 OID 0)
-- Dependencies: 236
-- Name: TABLE carbon_credit_transactions; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.carbon_credit_transactions TO app_user;
GRANT ALL ON TABLE public.carbon_credit_transactions TO app_admin;


--
-- TOC entry 5041 (class 0 OID 0)
-- Dependencies: 235
-- Name: SEQUENCE carbon_credit_transactions_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.carbon_credit_transactions_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.carbon_credit_transactions_id_seq TO app_admin;


--
-- TOC entry 5042 (class 0 OID 0)
-- Dependencies: 230
-- Name: TABLE carbon_credits; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.carbon_credits TO app_user;
GRANT ALL ON TABLE public.carbon_credits TO app_admin;


--
-- TOC entry 5044 (class 0 OID 0)
-- Dependencies: 229
-- Name: SEQUENCE carbon_credits_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.carbon_credits_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.carbon_credits_id_seq TO app_admin;


--
-- TOC entry 5045 (class 0 OID 0)
-- Dependencies: 234
-- Name: TABLE credit_transactions; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.credit_transactions TO app_user;
GRANT ALL ON TABLE public.credit_transactions TO app_admin;


--
-- TOC entry 5047 (class 0 OID 0)
-- Dependencies: 233
-- Name: SEQUENCE credit_transactions_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.credit_transactions_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.credit_transactions_id_seq TO app_admin;


--
-- TOC entry 5048 (class 0 OID 0)
-- Dependencies: 222
-- Name: TABLE emission_factors; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.emission_factors TO app_user;
GRANT ALL ON TABLE public.emission_factors TO app_admin;


--
-- TOC entry 5050 (class 0 OID 0)
-- Dependencies: 221
-- Name: SEQUENCE emission_factors_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.emission_factors_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.emission_factors_id_seq TO app_admin;


--
-- TOC entry 5051 (class 0 OID 0)
-- Dependencies: 226
-- Name: TABLE emissions; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.emissions TO app_user;
GRANT ALL ON TABLE public.emissions TO app_admin;


--
-- TOC entry 5053 (class 0 OID 0)
-- Dependencies: 225
-- Name: SEQUENCE emissions_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.emissions_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.emissions_id_seq TO app_admin;


--
-- TOC entry 5054 (class 0 OID 0)
-- Dependencies: 232
-- Name: TABLE marketplace_listings; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.marketplace_listings TO app_user;
GRANT ALL ON TABLE public.marketplace_listings TO app_admin;


--
-- TOC entry 5056 (class 0 OID 0)
-- Dependencies: 231
-- Name: SEQUENCE marketplace_listings_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.marketplace_listings_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.marketplace_listings_id_seq TO app_admin;


--
-- TOC entry 5057 (class 0 OID 0)
-- Dependencies: 224
-- Name: TABLE projects; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.projects TO app_user;
GRANT ALL ON TABLE public.projects TO app_admin;


--
-- TOC entry 5059 (class 0 OID 0)
-- Dependencies: 223
-- Name: SEQUENCE projects_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.projects_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.projects_id_seq TO app_admin;


--
-- TOC entry 5060 (class 0 OID 0)
-- Dependencies: 228
-- Name: TABLE recommendations; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.recommendations TO app_user;
GRANT ALL ON TABLE public.recommendations TO app_admin;


--
-- TOC entry 5062 (class 0 OID 0)
-- Dependencies: 227
-- Name: SEQUENCE recommendations_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.recommendations_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.recommendations_id_seq TO app_admin;


--
-- TOC entry 5063 (class 0 OID 0)
-- Dependencies: 218
-- Name: TABLE reports; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.reports TO app_user;
GRANT ALL ON TABLE public.reports TO app_admin;


--
-- TOC entry 5065 (class 0 OID 0)
-- Dependencies: 217
-- Name: SEQUENCE reports_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.reports_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.reports_id_seq TO app_admin;


--
-- TOC entry 5066 (class 0 OID 0)
-- Dependencies: 220
-- Name: TABLE users; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.users TO app_user;
GRANT ALL ON TABLE public.users TO app_admin;


--
-- TOC entry 5068 (class 0 OID 0)
-- Dependencies: 219
-- Name: SEQUENCE users_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.users_id_seq TO app_user;
GRANT ALL ON SEQUENCE public.users_id_seq TO app_admin;


-- Completed on 2025-12-24 02:22:24

--
-- PostgreSQL database dump complete
--

