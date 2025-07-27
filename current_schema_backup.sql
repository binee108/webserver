--
-- PostgreSQL database dump
--

-- Dumped from database version 15.13 (Debian 15.13-1.pgdg120+1)
-- Dumped by pg_dump version 15.13 (Debian 15.13-1.pgdg120+1)

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
-- Name: accounts; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.accounts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    exchange character varying(50) NOT NULL,
    public_api text NOT NULL,
    secret_api text NOT NULL,
    passphrase text,
    is_active boolean NOT NULL,
    updated_at timestamp without time zone,
    created_at timestamp without time zone
);


ALTER TABLE public.accounts OWNER TO trader;

--
-- Name: accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.accounts_id_seq OWNER TO trader;

--
-- Name: accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.accounts_id_seq OWNED BY public.accounts.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO trader;

--
-- Name: daily_account_summaries; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.daily_account_summaries (
    id integer NOT NULL,
    account_id integer NOT NULL,
    date date NOT NULL,
    starting_balance double precision NOT NULL,
    ending_balance double precision NOT NULL,
    total_pnl double precision NOT NULL,
    realized_pnl double precision NOT NULL,
    unrealized_pnl double precision NOT NULL,
    total_trades integer NOT NULL,
    winning_trades integer NOT NULL,
    losing_trades integer NOT NULL,
    win_rate double precision NOT NULL,
    max_drawdown double precision NOT NULL,
    total_volume double precision NOT NULL,
    total_fees double precision NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.daily_account_summaries OWNER TO trader;

--
-- Name: daily_account_summaries_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.daily_account_summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.daily_account_summaries_id_seq OWNER TO trader;

--
-- Name: daily_account_summaries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.daily_account_summaries_id_seq OWNED BY public.daily_account_summaries.id;


--
-- Name: open_orders; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.open_orders (
    id integer NOT NULL,
    strategy_account_id integer NOT NULL,
    exchange_order_id character varying(100) NOT NULL,
    symbol character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    price double precision NOT NULL,
    quantity double precision NOT NULL,
    filled_quantity double precision NOT NULL,
    status character varying(20) NOT NULL,
    market_type character varying(10) NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.open_orders OWNER TO trader;

--
-- Name: open_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.open_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.open_orders_id_seq OWNER TO trader;

--
-- Name: open_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.open_orders_id_seq OWNED BY public.open_orders.id;


--
-- Name: strategies; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.strategies (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    group_name character varying(100) NOT NULL,
    market_type character varying(10) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.strategies OWNER TO trader;

--
-- Name: strategies_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.strategies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.strategies_id_seq OWNER TO trader;

--
-- Name: strategies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.strategies_id_seq OWNED BY public.strategies.id;


--
-- Name: strategy_accounts; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.strategy_accounts (
    id integer NOT NULL,
    strategy_id integer NOT NULL,
    account_id integer NOT NULL,
    weight double precision NOT NULL,
    leverage double precision NOT NULL,
    max_symbols integer
);


ALTER TABLE public.strategy_accounts OWNER TO trader;

--
-- Name: strategy_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.strategy_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.strategy_accounts_id_seq OWNER TO trader;

--
-- Name: strategy_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.strategy_accounts_id_seq OWNED BY public.strategy_accounts.id;


--
-- Name: strategy_capital; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.strategy_capital (
    id integer NOT NULL,
    strategy_account_id integer NOT NULL,
    allocated_capital double precision NOT NULL,
    current_pnl double precision NOT NULL,
    last_updated timestamp without time zone
);


ALTER TABLE public.strategy_capital OWNER TO trader;

--
-- Name: strategy_capital_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.strategy_capital_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.strategy_capital_id_seq OWNER TO trader;

--
-- Name: strategy_capital_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.strategy_capital_id_seq OWNED BY public.strategy_capital.id;


--
-- Name: strategy_positions; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.strategy_positions (
    id integer NOT NULL,
    strategy_account_id integer NOT NULL,
    symbol character varying(20) NOT NULL,
    quantity double precision NOT NULL,
    entry_price double precision NOT NULL,
    last_updated timestamp without time zone
);


ALTER TABLE public.strategy_positions OWNER TO trader;

--
-- Name: strategy_positions_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.strategy_positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.strategy_positions_id_seq OWNER TO trader;

--
-- Name: strategy_positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.strategy_positions_id_seq OWNED BY public.strategy_positions.id;


--
-- Name: system_summaries; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.system_summaries (
    id integer NOT NULL,
    date date NOT NULL,
    total_balance double precision NOT NULL,
    total_pnl double precision NOT NULL,
    total_trades integer NOT NULL,
    active_accounts integer NOT NULL,
    active_strategies integer NOT NULL,
    system_mdd double precision NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.system_summaries OWNER TO trader;

--
-- Name: system_summaries_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.system_summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.system_summaries_id_seq OWNER TO trader;

--
-- Name: system_summaries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.system_summaries_id_seq OWNED BY public.system_summaries.id;


--
-- Name: trades; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.trades (
    id integer NOT NULL,
    strategy_account_id integer NOT NULL,
    exchange_order_id character varying(100) NOT NULL,
    symbol character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    order_type character varying(10) NOT NULL,
    order_price double precision,
    price double precision NOT NULL,
    quantity double precision NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    pnl double precision,
    fee double precision,
    is_entry boolean,
    market_type character varying(10) NOT NULL
);


ALTER TABLE public.trades OWNER TO trader;

--
-- Name: trades_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.trades_id_seq OWNER TO trader;

--
-- Name: trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.trades_id_seq OWNED BY public.trades.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(80) NOT NULL,
    password_hash character varying(255) NOT NULL,
    email character varying(120),
    telegram_id character varying(100),
    is_active boolean NOT NULL,
    is_admin boolean NOT NULL,
    must_change_password boolean NOT NULL,
    last_login timestamp without time zone,
    created_at timestamp without time zone
);


ALTER TABLE public.users OWNER TO trader;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.users_id_seq OWNER TO trader;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: webhook_logs; Type: TABLE; Schema: public; Owner: trader
--

CREATE TABLE public.webhook_logs (
    id integer NOT NULL,
    received_at timestamp without time zone,
    payload text NOT NULL,
    status character varying(20) NOT NULL,
    message text
);


ALTER TABLE public.webhook_logs OWNER TO trader;

--
-- Name: webhook_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: trader
--

CREATE SEQUENCE public.webhook_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.webhook_logs_id_seq OWNER TO trader;

--
-- Name: webhook_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: trader
--

ALTER SEQUENCE public.webhook_logs_id_seq OWNED BY public.webhook_logs.id;


--
-- Name: accounts id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.accounts ALTER COLUMN id SET DEFAULT nextval('public.accounts_id_seq'::regclass);


--
-- Name: daily_account_summaries id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.daily_account_summaries ALTER COLUMN id SET DEFAULT nextval('public.daily_account_summaries_id_seq'::regclass);


--
-- Name: open_orders id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.open_orders ALTER COLUMN id SET DEFAULT nextval('public.open_orders_id_seq'::regclass);


--
-- Name: strategies id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategies ALTER COLUMN id SET DEFAULT nextval('public.strategies_id_seq'::regclass);


--
-- Name: strategy_accounts id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_accounts ALTER COLUMN id SET DEFAULT nextval('public.strategy_accounts_id_seq'::regclass);


--
-- Name: strategy_capital id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_capital ALTER COLUMN id SET DEFAULT nextval('public.strategy_capital_id_seq'::regclass);


--
-- Name: strategy_positions id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_positions ALTER COLUMN id SET DEFAULT nextval('public.strategy_positions_id_seq'::regclass);


--
-- Name: system_summaries id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.system_summaries ALTER COLUMN id SET DEFAULT nextval('public.system_summaries_id_seq'::regclass);


--
-- Name: trades id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.trades ALTER COLUMN id SET DEFAULT nextval('public.trades_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: webhook_logs id; Type: DEFAULT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.webhook_logs ALTER COLUMN id SET DEFAULT nextval('public.webhook_logs_id_seq'::regclass);


--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: daily_account_summaries daily_account_summaries_account_id_date_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.daily_account_summaries
    ADD CONSTRAINT daily_account_summaries_account_id_date_key UNIQUE (account_id, date);


--
-- Name: daily_account_summaries daily_account_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.daily_account_summaries
    ADD CONSTRAINT daily_account_summaries_pkey PRIMARY KEY (id);


--
-- Name: open_orders open_orders_exchange_order_id_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.open_orders
    ADD CONSTRAINT open_orders_exchange_order_id_key UNIQUE (exchange_order_id);


--
-- Name: open_orders open_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.open_orders
    ADD CONSTRAINT open_orders_pkey PRIMARY KEY (id);


--
-- Name: strategies strategies_group_name_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_group_name_key UNIQUE (group_name);


--
-- Name: strategies strategies_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_pkey PRIMARY KEY (id);


--
-- Name: strategy_accounts strategy_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_accounts
    ADD CONSTRAINT strategy_accounts_pkey PRIMARY KEY (id);


--
-- Name: strategy_accounts strategy_accounts_strategy_id_account_id_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_accounts
    ADD CONSTRAINT strategy_accounts_strategy_id_account_id_key UNIQUE (strategy_id, account_id);


--
-- Name: strategy_capital strategy_capital_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_capital
    ADD CONSTRAINT strategy_capital_pkey PRIMARY KEY (id);


--
-- Name: strategy_capital strategy_capital_strategy_account_id_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_capital
    ADD CONSTRAINT strategy_capital_strategy_account_id_key UNIQUE (strategy_account_id);


--
-- Name: strategy_positions strategy_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_positions
    ADD CONSTRAINT strategy_positions_pkey PRIMARY KEY (id);


--
-- Name: strategy_positions strategy_positions_strategy_account_id_symbol_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_positions
    ADD CONSTRAINT strategy_positions_strategy_account_id_symbol_key UNIQUE (strategy_account_id, symbol);


--
-- Name: system_summaries system_summaries_date_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.system_summaries
    ADD CONSTRAINT system_summaries_date_key UNIQUE (date);


--
-- Name: system_summaries system_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.system_summaries
    ADD CONSTRAINT system_summaries_pkey PRIMARY KEY (id);


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: webhook_logs webhook_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.webhook_logs
    ADD CONSTRAINT webhook_logs_pkey PRIMARY KEY (id);


--
-- Name: accounts accounts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: daily_account_summaries daily_account_summaries_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.daily_account_summaries
    ADD CONSTRAINT daily_account_summaries_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id);


--
-- Name: open_orders open_orders_strategy_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.open_orders
    ADD CONSTRAINT open_orders_strategy_account_id_fkey FOREIGN KEY (strategy_account_id) REFERENCES public.strategy_accounts(id);


--
-- Name: strategies strategies_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: strategy_accounts strategy_accounts_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_accounts
    ADD CONSTRAINT strategy_accounts_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id);


--
-- Name: strategy_accounts strategy_accounts_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_accounts
    ADD CONSTRAINT strategy_accounts_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id);


--
-- Name: strategy_capital strategy_capital_strategy_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_capital
    ADD CONSTRAINT strategy_capital_strategy_account_id_fkey FOREIGN KEY (strategy_account_id) REFERENCES public.strategy_accounts(id);


--
-- Name: strategy_positions strategy_positions_strategy_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.strategy_positions
    ADD CONSTRAINT strategy_positions_strategy_account_id_fkey FOREIGN KEY (strategy_account_id) REFERENCES public.strategy_accounts(id);


--
-- Name: trades trades_strategy_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: trader
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_strategy_account_id_fkey FOREIGN KEY (strategy_account_id) REFERENCES public.strategy_accounts(id);


--
-- PostgreSQL database dump complete
--

