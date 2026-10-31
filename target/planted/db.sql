-- MySQL dump 10.13  Distrib 5.7.42, for Linux (x86_64)
--
-- Host: localhost    Database: jobnest_prod
-- ------------------------------------------------------
-- A2D 시연용 가짜 덤프. 지원자 이름·이메일·전화번호·이력서 경로는 모두 지어낸 값이다.

DROP TABLE IF EXISTS `applicants`;
CREATE TABLE `applicants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  `email` varchar(120) NOT NULL,
  `phone` varchar(20) NOT NULL,
  `birth` date DEFAULT NULL,
  `desired_job` varchar(50) DEFAULT NULL,
  `career_years` int DEFAULT 0,
  `resume_file` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

LOCK TABLES `applicants` WRITE;
INSERT INTO `applicants` VALUES
(1,'이서연','applicant001@example.com','010-0000-0001','1989-02-11','프런트엔드 개발자',1,'resumes/0001.pdf'),
(2,'박도윤','applicant002@example.com','010-0000-0002','1990-03-12','데이터 분석가',2,'resumes/0002.pdf'),
(3,'최하은','applicant003@example.com','010-0000-0003','1991-04-13','UX 디자이너',3,'resumes/0003.pdf'),
(4,'정시우','applicant004@example.com','010-0000-0004','1992-05-14','인사 담당자',4,'resumes/0004.pdf'),
(5,'강지우','applicant005@example.com','010-0000-0005','1993-06-15','영업 관리자',5,'resumes/0005.pdf'),
(6,'조주원','applicant006@example.com','010-0000-0006','1994-07-16','백엔드 개발자',6,'resumes/0006.pdf'),
(7,'윤서윤','applicant007@example.com','010-0000-0007','1995-08-17','프런트엔드 개발자',7,'resumes/0007.pdf'),
(8,'장예준','applicant008@example.com','010-0000-0008','1996-09-18','데이터 분석가',8,'resumes/0008.pdf'),
(9,'임지민','applicant009@example.com','010-0000-0009','1997-01-10','UX 디자이너',9,'resumes/0009.pdf'),
(10,'김건우','applicant010@example.com','010-0000-0010','1988-02-11','인사 담당자',10,'resumes/0010.pdf'),
(11,'이수아','applicant011@example.com','010-0000-0011','1989-03-12','영업 관리자',11,'resumes/0011.pdf'),
(12,'박현우','applicant012@example.com','010-0000-0012','1990-04-13','백엔드 개발자',0,'resumes/0012.pdf'),
(13,'최채원','applicant013@example.com','010-0000-0013','1991-05-14','프런트엔드 개발자',1,'resumes/0013.pdf'),
(14,'정우진','applicant014@example.com','010-0000-0014','1992-06-15','데이터 분석가',2,'resumes/0014.pdf'),
(15,'강다은','applicant015@example.com','010-0000-0015','1993-07-16','UX 디자이너',3,'resumes/0015.pdf'),
(16,'조선우','applicant016@example.com','010-0000-0016','1994-08-17','인사 담당자',4,'resumes/0016.pdf'),
(17,'윤예은','applicant017@example.com','010-0000-0017','1995-09-18','영업 관리자',5,'resumes/0017.pdf'),
(18,'장연우','applicant018@example.com','010-0000-0018','1996-01-10','백엔드 개발자',6,'resumes/0018.pdf'),
(19,'임소율','applicant019@example.com','010-0000-0019','1997-02-11','프런트엔드 개발자',7,'resumes/0019.pdf'),
(20,'김민준','applicant020@example.com','010-0000-0020','1988-03-12','데이터 분석가',8,'resumes/0020.pdf'),
(21,'이서연','applicant021@example.com','010-0000-0021','1989-04-13','UX 디자이너',9,'resumes/0021.pdf'),
(22,'박도윤','applicant022@example.com','010-0000-0022','1990-05-14','인사 담당자',10,'resumes/0022.pdf'),
(23,'최하은','applicant023@example.com','010-0000-0023','1991-06-15','영업 관리자',11,'resumes/0023.pdf'),
(24,'정시우','applicant024@example.com','010-0000-0024','1992-07-16','백엔드 개발자',0,'resumes/0024.pdf'),
(25,'강지우','applicant025@example.com','010-0000-0025','1993-08-17','프런트엔드 개발자',1,'resumes/0025.pdf'),
(26,'조주원','applicant026@example.com','010-0000-0026','1994-09-18','데이터 분석가',2,'resumes/0026.pdf'),
(27,'윤서윤','applicant027@example.com','010-0000-0027','1995-01-10','UX 디자이너',3,'resumes/0027.pdf'),
(28,'장예준','applicant028@example.com','010-0000-0028','1996-02-11','인사 담당자',4,'resumes/0028.pdf'),
(29,'임지민','applicant029@example.com','010-0000-0029','1997-03-12','영업 관리자',5,'resumes/0029.pdf'),
(30,'김건우','applicant030@example.com','010-0000-0030','1988-04-13','백엔드 개발자',6,'resumes/0030.pdf'),
(31,'이수아','applicant031@example.com','010-0000-0031','1989-05-14','프런트엔드 개발자',7,'resumes/0031.pdf'),
(32,'박현우','applicant032@example.com','010-0000-0032','1990-06-15','데이터 분석가',8,'resumes/0032.pdf'),
(33,'최채원','applicant033@example.com','010-0000-0033','1991-07-16','UX 디자이너',9,'resumes/0033.pdf'),
(34,'정우진','applicant034@example.com','010-0000-0034','1992-08-17','인사 담당자',10,'resumes/0034.pdf'),
(35,'강다은','applicant035@example.com','010-0000-0035','1993-09-18','영업 관리자',11,'resumes/0035.pdf'),
(36,'조선우','applicant036@example.com','010-0000-0036','1994-01-10','백엔드 개발자',0,'resumes/0036.pdf'),
(37,'윤예은','applicant037@example.com','010-0000-0037','1995-02-11','프런트엔드 개발자',1,'resumes/0037.pdf'),
(38,'장연우','applicant038@example.com','010-0000-0038','1996-03-12','데이터 분석가',2,'resumes/0038.pdf'),
(39,'임소율','applicant039@example.com','010-0000-0039','1997-04-13','UX 디자이너',3,'resumes/0039.pdf'),
(40,'김민준','applicant040@example.com','010-0000-0040','1988-05-14','인사 담당자',4,'resumes/0040.pdf');
UNLOCK TABLES;

-- Dump completed on 2026-09-30  3:12:44
