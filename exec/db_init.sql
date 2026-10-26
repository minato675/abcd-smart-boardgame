-- public.board_game definition

-- Drop table

-- DROP TABLE public.board_game;

CREATE TABLE public.board_game (
	board_game_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	"name" varchar(100) NOT NULL,
	min_players int2 NOT NULL,
	max_players int2 NOT NULL,
	difficulty varchar(20) NOT NULL,
	play_time int2 NULL,
	description text NULL,
	how_to_play text NULL,
	image_url varchar(500) NULL,
	CONSTRAINT board_game_pkey PRIMARY KEY (board_game_id)
);
CREATE INDEX idx_board_game_name ON public.board_game USING btree (name);
CREATE INDEX idx_board_game_players ON public.board_game USING btree (min_players, max_players);

INSERT INTO public.board_game ("name",min_players,max_players,difficulty,play_time,description,how_to_play,image_url) VALUES
	 ('스텔라',3,6,'NORMAL',30,'딕싯의 그림 카드로 즐기는 연상 단어 게임. 모두가 동시에 카드를 보고 떠오르는 단어를 적어, 남들과 겹칠수록 점수가 올라간다. 다만 욕심내다 아무와도 안 겹치면 그 라운드를 통째로 잃는다.','카드 펼치기: 이번 라운드에 쓸 그림 카드를 테이블 가운데에 펼칩니다.
단어 적기: 모래시계가 끝날 때까지 카드에서 떠오르는 단어를 각자 자기 보드에 적습니다.
겹치는 단어 확인: 한 명씩 단어를 말하고, 같은 단어를 적은 사람이 많을수록 높은 점수를 받습니다.
멈출지 정하기: 다음 단어로 넘어갈지 여기서 멈출지 고릅니다. 계속 가다 아무와도 안 겹치면 점수를 잃습니다.
점수 합산: 정해진 라운드를 마치면 별을 가장 많이 모은 사람이 이깁니다.',NULL),
	 ('할리갈리',2,6,'EASY',15,'종을 먼저 치는 사람이 임자. 카드를 한 장씩 뒤집다가 같은 과일이 정확히 5개 보이면 재빨리 종을 칩니다. 규칙은 30초면 배우지만 손은 계속 헛나갑니다.','카드 나누기: 카드를 모두에게 똑같이 나눠 주고, 그림이 안 보이게 자기 앞에 쌓습니다.
한 장씩 뒤집기: 차례대로 자기 더미에서 한 장을 뒤집어 자기 앞에 펼쳐 놓습니다.
5개 세기: 펼쳐진 카드 전체에서 같은 과일이 정확히 5개가 되는 순간을 노립니다.
종 치기: 가장 먼저 종을 친 사람이 펼쳐진 카드를 모두 가져갑니다.
잘못 쳤다면: 5개가 아닌데 종을 쳤으면 모두에게 카드를 한 장씩 물어 줍니다.
승리: 카드를 다 잃으면 탈락하고, 마지막까지 남은 사람이 이깁니다.',NULL),
	 ('딕싯',3,6,'EASY',30,'정답이 없는 그림으로 이야기하는 게임. 이야기꾼은 카드 한 장을 골라 한 마디를 던지고, 나머지는 그 말에 어울리는 카드를 몰래 섞어 넣습니다. 너무 쉬워도 너무 어려워도 점수가 안 됩니다.','카드 받기: 각자 그림 카드를 6장씩 손에 들고 시작합니다.
이야기 꺼내기: 이야기꾼이 손패에서 한 장을 골라 뒷면으로 내고, 떠오르는 단어나 문장을 말합니다.
카드 섞어 넣기: 나머지 사람은 그 말에 어울릴 만한 자기 카드를 한 장씩 골라 함께 섞습니다.
찾기: 펼쳐진 카드 중 이야기꾼의 카드가 무엇일지 각자 몰래 투표합니다.
점수: 전원이 맞히거나 아무도 못 맞히면 이야기꾼은 0점입니다. 일부만 맞혀야 점수를 받습니다.',NULL),
	 ('루미큐브',2,4,'EASY',45,'숫자 타일로 조합을 만들어 손에 든 타일을 먼저 다 내려놓는 클래식 게임. 이미 테이블에 놓인 조합을 마음대로 쪼개고 붙일 수 있어서, 한 장을 끼워 넣으려고 판 전체를 갈아엎는 순간이 이 게임의 백미다.','타일 나누기: 타일 106장을 뒤집어 섞고 각자 14장씩 가져옵니다. 남은 타일은 가운데에 더미로 둡니다.
조합 만들기: 같은 색 연속 숫자 3장 이상(런), 또는 같은 숫자 다른 색 3~4장(그룹)이 낼 수 있는 조합입니다.
첫 등록 30점: 처음 내려놓을 때는 자기 타일만으로 합이 30점 이상이어야 합니다. 못 채우면 한 장 가져가고 차례를 넘깁니다.
테이블 재배치: 등록을 마쳤다면 이미 놓인 조합을 자유롭게 쪼개고 붙여 자기 타일을 끼워 넣을 수 있습니다.
조커 쓰기: 조커는 아무 타일이나 대신합니다. 조커가 들어간 조합에 실제 타일을 넣어 주면 조커를 회수할 수 있습니다.
차례 마치기: 정리가 끝난 시점에 테이블의 모든 조합이 유효해야 합니다. 낼 게 없으면 더미에서 한 장 가져오고 넘깁니다.
승리: 손에 든 타일을 가장 먼저 모두 내려놓은 사람이 이깁니다.',NULL);

-- public.board_game_category definition

-- Drop table

-- DROP TABLE public.board_game_category;

CREATE TABLE public.board_game_category (
	board_game_id int8 NOT NULL,
	category_id int8 NOT NULL,
	CONSTRAINT board_game_category_pkey PRIMARY KEY (board_game_id, category_id)
);
CREATE INDEX idx_category_id ON public.board_game_category USING btree (category_id);

INSERT INTO public.board_game_category (board_game_id,category_id) VALUES
	 (1,1),
	 (13,2),
	 (14,2),
	 (15,2);

-- public.board_game_item definition

-- Drop table

-- DROP TABLE public.board_game_item;

CREATE TABLE public.board_game_item (
	item_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	board_game_id int8 NOT NULL,
	cabinet_id int8 NOT NULL,
	status varchar(20) DEFAULT 'available'::character varying NOT NULL,
	CONSTRAINT board_game_item_pkey PRIMARY KEY (item_id)
);
CREATE INDEX idx_item_game_status ON public.board_game_item USING btree (board_game_id, status);

INSERT INTO public.board_game_item (board_game_id,cabinet_id,status) VALUES
	 (13,1,'available'),
	 (1,1,'available'),
	 (15,2,'available'),
	 (14,2,'available');

-- public.cabinet definition

-- Drop table

-- DROP TABLE public.cabinet;

CREATE TABLE public.cabinet (
	cabinet_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	status varchar(20) DEFAULT 'closed'::character varying NOT NULL,
	CONSTRAINT cabinet_pkey PRIMARY KEY (cabinet_id)
);

INSERT INTO public.cabinet
(cabinet_id, status)
VALUES(2, 'closed');
INSERT INTO public.cabinet
(cabinet_id, status)
VALUES(1, 'closed');

-- public.cabinet_history definition

-- Drop table

-- DROP TABLE public.cabinet_history;

CREATE TABLE public.cabinet_history (
	cabinet_log_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	cabinet_id int8 NOT NULL,
	event_type varchar(20) NOT NULL,
	triggered_by varchar(20) DEFAULT 'USER'::character varying NOT NULL,
	created_at timestamp DEFAULT now() NOT NULL,
	step int4 NOT NULL,
	transaction_id varchar NOT NULL,
	CONSTRAINT cabinet_history_pkey PRIMARY KEY (cabinet_log_id)
);
CREATE INDEX idx_cabinet_log_cabinet_time ON public.cabinet_history USING btree (cabinet_id, created_at);

-- public.cabinet_transaction definition

-- Drop table

-- DROP TABLE public.cabinet_transaction;

CREATE TABLE public.cabinet_transaction (
	transaction_id varchar NOT NULL,
	card_uid varchar NOT NULL,
	created_at timestamp DEFAULT now() NOT NULL,
	room_number varchar NOT NULL,
	CONSTRAINT cabinet_transaction_pk PRIMARY KEY (transaction_id)
);

-- public.category definition

-- Drop table

-- DROP TABLE public.category;

CREATE TABLE public.category (
	category_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	"name" varchar(50) NOT NULL,
	CONSTRAINT category_name_key UNIQUE (name),
	CONSTRAINT category_pkey PRIMARY KEY (category_id)
);

INSERT INTO public.category
(category_id, "name")
VALUES(1, '전략');
INSERT INTO public.category
(category_id, "name")
VALUES(2, '파티');
INSERT INTO public.category
(category_id, "name")
VALUES(3, '추리');

-- public.mc_turn_log definition

-- Drop table

-- DROP TABLE public.mc_turn_log;

CREATE TABLE public.mc_turn_log (
	turn_log_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	session_id uuid NOT NULL,
	room_number varchar(10) NOT NULL,
	turn_no int4 NOT NULL,
	tile_count int4 NOT NULL,
	table_state jsonb NOT NULL,
	created_at timestamp DEFAULT now() NOT NULL,
	CONSTRAINT mc_turn_log_pkey PRIMARY KEY (turn_log_id),
	CONSTRAINT uq_mc_turn_log_session_turn UNIQUE (session_id, turn_no)
);
CREATE INDEX idx_mc_turn_log_room_created ON public.mc_turn_log USING btree (room_number, created_at DESC);
CREATE INDEX idx_mc_turn_log_session ON public.mc_turn_log USING btree (session_id, turn_no);

-- public.mc_violation_log definition

-- Drop table

-- DROP TABLE public.mc_violation_log;

CREATE TABLE public.mc_violation_log (
	violation_log_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	session_id uuid NOT NULL,
	room_number varchar(10) NOT NULL,
	code varchar(50) NOT NULL,
	message text NOT NULL,
	created_at timestamp DEFAULT now() NOT NULL,
	board_game_id int8 NULL,
	table_state jsonb NULL,
	CONSTRAINT mc_violation_log_pkey PRIMARY KEY (violation_log_id),
	CONSTRAINT mc_violation_log_board_game_id_fkey FOREIGN KEY (board_game_id) REFERENCES public.board_game(board_game_id)
);
CREATE INDEX idx_mc_violation_code ON public.mc_violation_log USING btree (code, created_at DESC);
CREATE INDEX idx_mc_violation_game_code ON public.mc_violation_log USING btree (board_game_id, code);
CREATE INDEX idx_mc_violation_session ON public.mc_violation_log USING btree (session_id, created_at);

-- public.qna_log definition

-- Drop table

-- DROP TABLE public.qna_log;

CREATE TABLE public.qna_log (
	qna_log_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	transaction_id uuid NOT NULL,
	room_number varchar(10) NOT NULL,
	board_game_id int8 NULL,
	req text NULL,
	res text NOT NULL,
	created_at timestamp DEFAULT now() NOT NULL,
	CONSTRAINT qna_log_pkey PRIMARY KEY (qna_log_id),
	CONSTRAINT qna_log_board_game_id_fkey FOREIGN KEY (board_game_id) REFERENCES public.board_game(board_game_id)
);
CREATE INDEX idx_qna_log_room_created ON public.qna_log USING btree (room_number, created_at DESC);
CREATE INDEX idx_qna_log_transaction ON public.qna_log USING btree (transaction_id, created_at);

-- public.rent definition

-- Drop table

-- DROP TABLE public.rent;

CREATE TABLE public.rent (
	rent_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	board_game_id int8 NOT NULL,
	room_number varchar(10) NOT NULL,
	rented_at timestamp DEFAULT now() NOT NULL,
	returned_at timestamp NULL,
	play_time_sec int4 NULL,
	board_game_item_id int8 NOT NULL,
	status varchar(10) DEFAULT 'rent'::character varying NOT NULL,
	CONSTRAINT rent_pkey PRIMARY KEY (rent_id)
);
CREATE INDEX idx_rental_board_game ON public.rent USING btree (board_game_id);
CREATE INDEX idx_rental_room ON public.rent USING btree (room_number);

-- public.reservation definition

-- Drop table

-- DROP TABLE public.reservation;

CREATE TABLE public.reservation (
	reservation_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	board_game_id int8 NOT NULL,
	room_number varchar(10) NOT NULL,
	reserved_at timestamp DEFAULT now() NOT NULL,
	fulfilled_at timestamp NULL,
	cancelled_at timestamp NULL,
	status varchar(20) DEFAULT 'waiting'::character varying NOT NULL,
	CONSTRAINT reservation_pkey PRIMARY KEY (reservation_id)
);
CREATE INDEX idx_reservation_board_game ON public.reservation USING btree (board_game_id, status, reserved_at);
CREATE UNIQUE INDEX uq_reservation_waiting_room ON public.reservation USING btree (room_number) WHERE ((status)::text = 'WAITING'::text);

-- public.room definition

-- Drop table

-- DROP TABLE public.room;

CREATE TABLE public.room (
	room_number varchar(10) NOT NULL,
	capacity int2 NULL,
	status varchar(20) DEFAULT 'empty'::character varying NOT NULL,
	CONSTRAINT room_pkey PRIMARY KEY (room_number)
);

INSERT INTO public.room
(room_number, capacity, status)
VALUES('4', 4, 'empty');
INSERT INTO public.room
(room_number, capacity, status)
VALUES('3', 6, 'empty');
INSERT INTO public.room
(room_number, capacity, status)
VALUES('5', 4, 'empty');
INSERT INTO public.room
(room_number, capacity, status)
VALUES('6', 8, 'empty');
INSERT INTO public.room
(room_number, capacity, status)
VALUES('room-01', 8, 'empty');
INSERT INTO public.room
(room_number, capacity, status)
VALUES('2', 4, 'empty');

-- public.room_rfid definition

-- Drop table

-- DROP TABLE public.room_rfid;

CREATE TABLE public.room_rfid (
	controller_id varchar NOT NULL,
	rfid varchar NOT NULL,
	room_number varchar NOT NULL,
	CONSTRAINT room_rfid_pk PRIMARY KEY (controller_id, rfid)
);

INSERT INTO public.room_rfid
(controller_id, rfid, room_number)
VALUES('rpi-01', '680069A502', '2');
INSERT INTO public.room_rfid
(controller_id, rfid, room_number)
VALUES('rpi-01', '68006951C6', '3');
INSERT INTO public.room_rfid
(controller_id, rfid, room_number)
VALUES('rpi-01', '6800692765', '4');
INSERT INTO public.room_rfid
(controller_id, rfid, room_number)
VALUES('rpi-01', '6800695841', '5');
INSERT INTO public.room_rfid
(controller_id, rfid, room_number)
VALUES('rpi-01', '6800698FB1', '6');
INSERT INTO public.room_rfid
(controller_id, rfid, room_number)
VALUES('rpi-01', '680069DD2B', 'room-01');

-- public.room_usage definition

-- Drop table

-- DROP TABLE public.room_usage;

CREATE TABLE public.room_usage (
	room_usage_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	room_number varchar(10) NOT NULL,
	start_time timestamp DEFAULT now() NOT NULL,
	end_time timestamp NULL,
	CONSTRAINT room_usage_pkey PRIMARY KEY (room_usage_id)
);
CREATE INDEX idx_room_usage_room ON public.room_usage USING btree (room_number, end_time);