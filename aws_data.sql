--
-- PostgreSQL database dump
--

-- Dumped from database version 17.5
-- Dumped by pg_dump version 17.5

-- Started on 2025-12-24 02:36:47

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
-- TOC entry 4981 (class 0 OID 99975)
-- Dependencies: 220
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, username, email, created_at, password_hash, role) FROM stdin;
1	Harsh	Harsh@gmail.com	2025-08-21 10:21:28.42217	hash	user
2	Demo	Demo@gmail.com	2025-08-21 10:28:29.094993	hash	user
3	Pruthvi	Pruthvi@gmail.com	2025-08-26 19:17:05.708274	hash	user
13	seller_1a9296fd	seller_1a9296fd@test.com	2025-12-22 15:53:35.522739	hash	user
14	buyer_425063db	buyer_425063db@test.com	2025-12-22 15:53:35.522739	hash	user
15	seller_72039c80	seller_72039c80@test.com	2025-12-22 15:54:00.658413	hash	user
16	buyer_efafb77e	buyer_efafb77e@test.com	2025-12-22 15:54:00.658413	hash	user
17	seller_4e316a13	seller_4e316a13@test.com	2025-12-22 15:54:56.282342	hash	user
18	buyer_90e8e420	buyer_90e8e420@test.com	2025-12-22 15:54:56.282342	hash	user
19	seller_e532a9c1	seller_e532a9c1@test.com	2025-12-22 15:55:25.538866	hash	user
20	buyer_26cf5176	buyer_26cf5176@test.com	2025-12-22 15:55:25.538866	hash	user
21	seller_4e0e5e30	seller_4e0e5e30@test.com	2025-12-22 15:58:52.616417	hash	user
22	buyer_d7100bd7	buyer_d7100bd7@test.com	2025-12-22 15:58:52.616417	hash	user
23	meet	meet@gmail.com	2025-12-24 00:22:07.164808	scrypt:32768:8:1$oYqzBZW426ZdE38j$3f2569737413d4172739302d9548199d6da14095df37f7e023830354db774b5b61f38c220d0c3af85b2290d0428b3c77db04a906c7522761935dfd536a38b79e	user
\.


--
-- TOC entry 4985 (class 0 OID 99999)
-- Dependencies: 224
-- Data for Name: projects; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.projects (id, user_id, name, type, location, start_date, end_date, status, created_at) FROM stdin;
1	1	Green Highway Construction	Highway	California, USA	2024-01-15	2024-12-31	Active	2025-11-23 23:42:48.704667
2	1	Urban Bridge Renovation	Bridge	New York, USA	2024-03-01	2024-11-30	Active	2025-11-23 23:42:48.704667
3	1	Sustainable Parking Structure	Building	Texas, USA	2023-06-01	2024-05-31	Completed	2025-11-23 23:42:48.704667
4	1	Eco-Friendly Tunnel Project	Tunnel	Colorado, USA	2024-02-01	2025-01-31	Active	2025-11-23 23:42:48.704667
5	2	Solar-Powered Road Network	Highway	Arizona, USA	2024-04-01	2024-12-15	Active	2025-11-23 23:42:48.704667
6	2	Green Airport Expansion	Airport	Florida, USA	2023-09-01	2024-08-31	Completed	2025-11-23 23:42:48.704667
7	2	Recycled Materials Highway	Highway	Oregon, USA	2024-05-15	2025-03-31	Active	2025-11-23 23:42:48.704667
8	3	Smart City Infrastructure	Building	Washington, USA	2024-01-10	2024-10-31	Active	2025-11-23 23:42:48.704667
9	3	Low-Carbon Railway Extension	Railway	Illinois, USA	2023-11-01	2024-09-30	Active	2025-11-23 23:42:48.704667
10	3	Sustainable Port Development	Port	Georgia, USA	2024-06-01	2025-05-31	Active	2025-11-23 23:42:48.704667
51	13	Seller Project	Wind	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:53:35.522739
52	14	Buyer Project	Building	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:53:35.522739
53	15	Seller Project	Wind	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:54:00.658413
54	16	Buyer Project	Building	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:54:00.658413
55	17	Seller Project	Wind	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:54:56.282342
56	18	Buyer Project	Building	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:54:56.282342
57	19	Seller Project	Wind	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:55:25.538866
58	20	Buyer Project	Building	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:55:25.538866
59	21	Seller Project	Wind	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:58:52.616417
60	22	Buyer Project	Building	\N	2025-01-01	2025-12-31	In Progress	2025-12-22 15:58:52.616417
\.


--
-- TOC entry 4991 (class 0 OID 100056)
-- Dependencies: 230
-- Data for Name: carbon_credits; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.carbon_credits (id, project_id, user_id, credits_earned, credits_used, listed_quantity, credit_value, transaction_type, status, issued_at, created_at, source) FROM stdin;
54	59	21	100.00	5.00	5.00	10000.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 15:58:52.616417	ISSUANCE
55	60	22	5.00	0.00	0.00	250.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 15:58:53.264739	PURCHASED
57	2	1	1.00	0.00	0.00	1000.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 17:35:11.906539	PURCHASED
37	6	2	68.20	1.50	10.50	68200.00	ISSUANCE	available	2024-01-15	2025-11-23 23:44:15.536566	ISSUANCE
58	3	1	0.50	0.00	0.00	500.00	ISSUANCE	AVAILABLE	2025-12-23	2025-12-23 17:00:35.879771	PURCHASED
32	1	1	45.50	0.00	0.00	45500.00	ISSUANCE	available	2024-02-01	2025-11-23 23:44:15.536566	ISSUANCE
33	2	1	32.80	0.00	0.00	32800.00	ISSUANCE	available	2024-04-15	2025-11-23 23:44:15.536566	ISSUANCE
34	3	1	28.50	0.00	0.00	28500.00	ISSUANCE	available	2024-06-01	2025-11-23 23:44:15.536566	ISSUANCE
35	4	1	52.30	0.00	0.00	52300.00	ISSUANCE	available	2024-03-10	2025-11-23 23:44:15.536566	ISSUANCE
36	5	2	58.70	0.00	0.00	58700.00	ISSUANCE	available	2024-05-20	2025-11-23 23:44:15.536566	ISSUANCE
38	7	2	72.50	0.00	0.00	72500.00	ISSUANCE	available	2024-06-10	2025-11-23 23:44:15.536566	ISSUANCE
39	8	3	42.30	0.00	0.00	42300.00	ISSUANCE	available	2024-02-20	2025-11-23 23:44:15.536566	ISSUANCE
40	9	3	55.80	0.00	0.00	55800.00	ISSUANCE	available	2024-01-05	2025-11-23 23:44:15.536566	ISSUANCE
41	10	3	62.40	0.00	0.00	62400.00	ISSUANCE	available	2024-07-01	2025-11-23 23:44:15.536566	ISSUANCE
46	6	2	10.00	0.00	0.00	72500.00	ISSUANCE	available	2024-11-24	2025-11-24 22:55:36.452162	ISSUANCE
50	51	13	100.00	0.00	10.00	10000.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 15:53:35.522739	ISSUANCE
51	53	15	100.00	0.00	10.00	10000.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 15:54:00.658413	ISSUANCE
52	55	17	100.00	0.00	10.00	10000.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 15:54:56.282342	ISSUANCE
53	57	19	100.00	0.00	10.00	10000.00	ISSUANCE	AVAILABLE	2025-12-22	2025-12-22 15:55:25.538866	ISSUANCE
\.


--
-- TOC entry 4993 (class 0 OID 100082)
-- Dependencies: 232
-- Data for Name: marketplace_listings; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.marketplace_listings (id, credit_id, seller_id, quantity_available, price_per_credit, status, listed_at) FROM stdin;
14	50	13	10.00	50.00	active	2025-12-22 15:53:35.653631
15	51	15	10.00	50.00	active	2025-12-22 15:54:00.763567
16	52	17	10.00	50.00	active	2025-12-22 15:54:56.405344
17	53	19	10.00	50.00	active	2025-12-22 15:55:25.692699
18	54	21	5.00	50.00	active	2025-12-22 15:58:52.863995
13	37	2	10.50	1000.00	active	2025-12-22 14:48:56.811518
\.


--
-- TOC entry 4997 (class 0 OID 100201)
-- Dependencies: 236
-- Data for Name: carbon_credit_transactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.carbon_credit_transactions (id, from_user_id, to_user_id, quantity, price_per_credit, total_price, from_project_id, to_project_id, listing_id, transaction_type, status, payment_reference, created_at, updated_at) FROM stdin;
1	21	22	5.00	50.00	250.00	59	60	18	PURCHASE	COMPLETED	PAY_AA99AC75D446	2025-12-22 15:58:53.264739	2025-12-22 15:58:53.264739
2	2	1	1.00	1000.00	1000.00	6	2	13	PURCHASE	COMPLETED	LEGACY_PAYMENT	2025-12-22 17:35:11.906539	2025-12-22 17:35:11.906539
3	2	1	0.50	1000.00	500.00	6	3	13	PURCHASE	COMPLETED	LEGACY_PAYMENT	2025-12-23 17:00:35.879771	2025-12-23 17:00:35.879771
\.


--
-- TOC entry 4995 (class 0 OID 100104)
-- Dependencies: 234
-- Data for Name: credit_transactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.credit_transactions (id, listing_id, buyer_id, seller_id, credit_id, quantity, total_price, transaction_date) FROM stdin;
\.


--
-- TOC entry 4983 (class 0 OID 99989)
-- Dependencies: 222
-- Data for Name: emission_factors; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.emission_factors (id, name, co2e_per_unit, unit, category, created_at) FROM stdin;
1	Asphalt	0.0234	kg CO2e/kg	Materials	2025-11-23 22:13:13.797951
2	Aggregate	0.0048	kg CO2e/kg	Materials	2025-11-23 22:13:13.801684
3	Cement	0.9300	kg CO2e/kg	Materials	2025-11-23 22:13:13.802507
4	Steel	1.8500	kg CO2e/kg	Materials	2025-11-23 22:13:13.804239
5	Diesel	2.6800	kg CO2e/L	Fuel	2025-11-23 22:13:13.805185
6	Electricity	0.5200	kg CO2e/kWh	Energy	2025-11-23 22:13:13.805973
7	Transport	0.0620	kg CO2e/tkm	Logistics	2025-11-23 22:13:13.808395
\.


--
-- TOC entry 4987 (class 0 OID 100015)
-- Dependencies: 226
-- Data for Name: emissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.emissions (id, project_id, asphalt_t, aggregate_t, cement_t, steel_t, diesel_l, electricity_kwh, transport_tkm, water_use, waste_t, recycled_pct, renewable_pct, created_at) FROM stdin;
31	1	1200.50	3500.75	450.25	280.00	8500.00	12000.00	4500.00	2500.00	120.00	35.00	25.00	2025-11-23 23:43:49.884549
32	2	450.00	1200.00	800.50	650.00	4200.00	8500.00	2800.00	1500.00	85.00	45.00	30.00	2025-11-23 23:43:49.884549
33	3	320.00	850.00	550.00	420.00	2800.00	6500.00	1900.00	1200.00	65.00	55.00	40.00	2025-11-23 23:43:49.884549
34	4	680.00	2200.00	1200.00	850.00	6500.00	15000.00	3500.00	2800.00	145.00	40.00	35.00	2025-11-23 23:43:49.884549
35	5	950.00	2800.00	380.00	320.00	5200.00	9500.00	3200.00	1800.00	95.00	50.00	60.00	2025-11-23 23:43:49.884549
36	6	1500.00	4200.00	950.00	780.00	11000.00	22000.00	5500.00	3500.00	180.00	38.00	45.00	2025-11-23 23:43:49.884549
37	7	1100.00	3200.00	420.00	350.00	7200.00	11000.00	3800.00	2200.00	110.00	65.00	50.00	2025-11-23 23:43:49.884549
38	8	580.00	1650.00	720.00	550.00	4800.00	14000.00	2600.00	1900.00	92.00	48.00	55.00	2025-11-23 23:43:49.884549
39	9	420.00	1800.00	880.00	920.00	5500.00	18000.00	3100.00	2400.00	125.00	42.00	48.00	2025-11-23 23:43:49.884549
40	10	1350.00	3800.00	1100.00	890.00	9500.00	20000.00	4800.00	3200.00	165.00	36.00	42.00	2025-11-23 23:43:49.884549
\.


--
-- TOC entry 4989 (class 0 OID 100039)
-- Dependencies: 228
-- Data for Name: recommendations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.recommendations (id, project_id, title, description, impact, cost, category, display_order, is_active, created_at) FROM stdin;
1	1	Use Recycled Asphalt	Incorporate 50% recycled asphalt pavement (RAP) to reduce virgin material usage	High	15000.00	Materials	1	t	2025-11-23 23:44:35.926348
2	1	Solar-Powered Equipment	Replace diesel equipment with solar-powered alternatives where possible	Medium	45000.00	Energy	2	t	2025-11-23 23:44:35.926348
3	1	Optimize Transport Routes	Use route optimization software to reduce transport emissions by 20%	Medium	5000.00	Logistics	3	t	2025-11-23 23:44:35.926348
4	2	Low-Carbon Concrete	Use supplementary cementitious materials to reduce cement content by 30%	High	22000.00	Materials	1	t	2025-11-23 23:44:35.926348
5	2	LED Construction Lighting	Replace traditional lighting with LED systems	Low	8000.00	Energy	2	t	2025-11-23 23:44:35.926348
6	3	Green Roof Installation	Add vegetated roof to reduce heat island effect	Medium	35000.00	Building Design	1	t	2025-11-23 23:44:35.926348
7	3	Rainwater Harvesting	Install rainwater collection system for non-potable water use	Medium	18000.00	Water Management	2	t	2025-11-23 23:44:35.926348
8	3	EV Charging Stations	Include electric vehicle charging infrastructure	High	25000.00	Future-Proofing	3	t	2025-11-23 23:44:35.926348
9	4	Tunnel Ventilation Optimization	Install smart ventilation system to reduce energy consumption	High	65000.00	Energy	1	t	2025-11-23 23:44:35.926348
10	4	Geothermal Heating	Use geothermal energy for tunnel climate control	High	85000.00	Energy	2	t	2025-11-23 23:44:35.926348
11	5	Expand Solar Panel Coverage	Increase solar panel installation along road shoulders	High	120000.00	Energy	1	t	2025-11-23 23:44:35.926348
12	5	Permeable Pavement	Use permeable materials to improve stormwater management	Medium	32000.00	Water Management	2	t	2025-11-23 23:44:35.926348
13	5	Native Vegetation Landscaping	Plant drought-resistant native species to reduce water use	Low	12000.00	Landscaping	3	t	2025-11-23 23:44:35.926348
14	6	Airport Solar Farm	Develop on-site solar generation to power 40% of airport operations	High	250000.00	Energy	1	t	2025-11-23 23:44:35.926348
15	6	Electric Ground Support Equipment	Replace diesel-powered GSE with electric alternatives	High	180000.00	Equipment	2	t	2025-11-23 23:44:35.926348
16	7	Increase Recycled Content	Boost recycled aggregate usage from 65% to 80%	High	18000.00	Materials	1	t	2025-11-23 23:44:35.926348
17	7	Bio-Based Asphalt Additives	Use bio-based rejuvenators instead of petroleum-based products	Medium	28000.00	Materials	2	t	2025-11-23 23:44:35.926348
18	7	Carbon Capture Concrete	Pilot carbon-absorbing concrete in select sections	High	55000.00	Innovation	3	t	2025-11-23 23:44:35.926348
19	8	Smart Grid Integration	Connect buildings to smart grid for optimized energy distribution	High	95000.00	Energy	1	t	2025-11-23 23:44:35.926348
20	8	District Heating System	Implement centralized heating using waste heat recovery	High	150000.00	Energy	2	t	2025-11-23 23:44:35.926348
21	8	Green Building Certification	Pursue LEED Platinum certification for all structures	Medium	45000.00	Certification	3	t	2025-11-23 23:44:35.926348
22	9	Regenerative Braking Systems	Install energy recovery systems on all rail vehicles	High	220000.00	Energy	1	t	2025-11-23 23:44:35.926348
23	9	Electrify Entire Line	Complete electrification to eliminate diesel locomotives	High	450000.00	Infrastructure	2	t	2025-11-23 23:44:35.926348
24	10	Shore Power Infrastructure	Install shore-to-ship power to reduce vessel emissions at berth	High	320000.00	Energy	1	t	2025-11-23 23:44:35.926348
25	10	Automated Container Handling	Deploy electric automated guided vehicles for container movement	High	280000.00	Equipment	2	t	2025-11-23 23:44:35.926348
26	10	Port Microgrid	Develop renewable energy microgrid with battery storage	High	500000.00	Energy	3	t	2025-11-23 23:44:35.926348
\.


--
-- TOC entry 4979 (class 0 OID 57987)
-- Dependencies: 218
-- Data for Name: reports; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reports (id, user_id, project_id, name, file_path, file_size, created_at) FROM stdin;
\.


--
-- TOC entry 5003 (class 0 OID 0)
-- Dependencies: 235
-- Name: carbon_credit_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.carbon_credit_transactions_id_seq', 3, true);


--
-- TOC entry 5004 (class 0 OID 0)
-- Dependencies: 229
-- Name: carbon_credits_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.carbon_credits_id_seq', 61, true);


--
-- TOC entry 5005 (class 0 OID 0)
-- Dependencies: 233
-- Name: credit_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.credit_transactions_id_seq', 1, false);


--
-- TOC entry 5006 (class 0 OID 0)
-- Dependencies: 221
-- Name: emission_factors_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.emission_factors_id_seq', 7, true);


--
-- TOC entry 5007 (class 0 OID 0)
-- Dependencies: 225
-- Name: emissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.emissions_id_seq', 43, true);


--
-- TOC entry 5008 (class 0 OID 0)
-- Dependencies: 231
-- Name: marketplace_listings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.marketplace_listings_id_seq', 18, true);


--
-- TOC entry 5009 (class 0 OID 0)
-- Dependencies: 223
-- Name: projects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.projects_id_seq', 65, true);


--
-- TOC entry 5010 (class 0 OID 0)
-- Dependencies: 227
-- Name: recommendations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.recommendations_id_seq', 36, true);


--
-- TOC entry 5011 (class 0 OID 0)
-- Dependencies: 217
-- Name: reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reports_id_seq', 1, true);


--
-- TOC entry 5012 (class 0 OID 0)
-- Dependencies: 219
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 24, true);


-- Completed on 2025-12-24 02:36:47

--
-- PostgreSQL database dump complete
--

