-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: May 31, 2025 at 12:56 PM
-- Server version: 10.4.28-MariaDB
-- PHP Version: 8.2.4

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `Health_Guide`
--

-- --------------------------------------------------------

--
-- Table structure for table `admins`
--

CREATE TABLE `admins` (
  `user_id` int(11) NOT NULL,
  `admin_level` enum('super','regular') DEFAULT 'regular'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `admins`
--

INSERT INTO `admins` (`user_id`, `admin_level`) VALUES
(42, 'super'),
(50, 'super');

-- --------------------------------------------------------

--
-- Table structure for table `allergies`
--

CREATE TABLE `allergies` (
  `allergy_id` int(11) NOT NULL,
  `allergy_name` varchar(100) NOT NULL,
  `allergy_type` enum('medication','food','environmental','other') NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `allergies`
--

INSERT INTO `allergies` (`allergy_id`, `allergy_name`, `allergy_type`, `created_at`, `updated_at`) VALUES
(1, 'Milk', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(2, 'Eggs', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(3, 'Peanuts', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(4, 'Tree Nuts (e.g., Almonds, Walnuts, Cashews)', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(5, 'Soy', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(6, 'Wheat (Gluten)', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(7, 'Fish (e.g., Cod, Salmon, Tuna)', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(8, 'Shellfish (e.g., Shrimp, Crab, Lobster)', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(9, 'Sesame', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(10, 'Mustard', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(11, 'Celery', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(12, 'Lupin', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(13, 'Sulphites/Sulfites', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(14, 'Corn', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(15, 'Citrus Fruits', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(16, 'Berries (e.g., Strawberries)', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(17, 'Nightshades (e.g., Tomatoes, Potatoes, Eggplant)', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(18, 'Kiwi', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(19, 'Avocado', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(20, 'Banana', 'food', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(21, 'Penicillin', 'medication', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(22, 'Aspirin', 'medication', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(23, 'Ibuprofen', 'medication', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(24, 'Sulfa drugs', 'medication', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(25, 'Pollen (e.g., Ragweed, Grass, Tree)', 'environmental', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(26, 'Dust Mites', 'environmental', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(27, 'Animal Dander (e.g., Cat, Dog)', 'environmental', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(28, 'Mold Spores', 'environmental', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(29, 'Latex', 'other', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(30, 'Nickel', 'other', '2025-05-29 19:59:59', '2025-05-29 19:59:59'),
(31, 'Fragrance', 'other', '2025-05-29 19:59:59', '2025-05-29 19:59:59');

-- --------------------------------------------------------

--
-- Table structure for table `appointments`
--

CREATE TABLE `appointments` (
  `appointment_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL,
  `appointment_date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `appointment_type_id` int(11) DEFAULT NULL,
  `status` enum('scheduled','completed','canceled','no-show','rescheduled') DEFAULT 'scheduled',
  `reschedule_count` int(11) NOT NULL DEFAULT 0,
  `reason` text DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `check_in_time` datetime DEFAULT NULL,
  `start_treatment_time` datetime DEFAULT NULL,
  `end_treatment_time` datetime DEFAULT NULL,
  `doctor_location_id` int(11) DEFAULT NULL COMMENT 'FK to doctor_locations.doctor_location_id',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_by` int(11) NOT NULL,
  `updated_by` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `appointments`
--

INSERT INTO `appointments` (`appointment_id`, `patient_id`, `doctor_id`, `appointment_date`, `start_time`, `end_time`, `appointment_type_id`, `status`, `reschedule_count`, `reason`, `notes`, `check_in_time`, `start_treatment_time`, `end_treatment_time`, `doctor_location_id`, `created_at`, `updated_at`, `created_by`, `updated_by`) VALUES
(12, 46, 43, '2025-05-18', '12:00:00', '12:20:00', 8, 'rescheduled', 1, '', NULL, NULL, NULL, NULL, 2, '2025-05-12 10:09:56', '2025-05-12 10:10:07', 46, 46),
(13, 46, 43, '2025-05-25', '12:30:00', '12:50:00', 8, 'canceled', 0, '', NULL, NULL, NULL, NULL, 2, '2025-05-12 10:10:20', '2025-05-12 10:11:58', 46, 46),
(14, 46, 43, '2025-05-18', '12:30:00', '12:50:00', 7, 'completed', 0, NULL, NULL, NULL, NULL, NULL, 2, '2025-05-12 19:01:39', '2025-05-13 21:49:26', 43, 43),
(15, 46, 43, '2025-05-18', '15:00:00', '15:20:00', 7, 'completed', 0, NULL, NULL, NULL, NULL, NULL, 2, '2025-05-13 21:50:33', '2025-05-13 21:50:38', 43, 43),
(16, 46, 43, '2025-05-25', '15:30:00', '15:50:00', 7, 'canceled', 1, NULL, NULL, NULL, NULL, NULL, 2, '2025-05-13 21:52:33', '2025-05-24 17:22:44', 46, 43),
(17, 46, 43, '2025-05-25', '15:00:00', '15:20:00', 7, 'rescheduled', 1, '', NULL, NULL, NULL, NULL, 2, '2025-05-24 19:37:51', '2025-05-24 19:37:59', 46, 46),
(18, 46, 43, '2025-05-25', '10:00:00', '10:20:00', 7, 'rescheduled', 1, '', NULL, NULL, NULL, NULL, 4, '2025-05-24 19:38:10', '2025-05-24 19:57:31', 46, 46),
(19, 46, 43, '2025-05-25', '10:00:00', '10:20:00', 7, 'canceled', 0, '', NULL, NULL, NULL, NULL, 4, '2025-05-24 19:57:47', '2025-05-24 19:58:01', 46, 46),
(21, 46, 43, '2025-06-01', '19:30:00', '19:50:00', 7, 'rescheduled', 1, '', NULL, NULL, NULL, NULL, 2, '2025-05-25 21:09:41', '2025-05-25 21:09:50', 46, 46),
(22, 46, 43, '2025-06-08', '15:30:00', '15:50:00', 7, 'rescheduled', 1, '', NULL, NULL, NULL, NULL, 2, '2025-05-25 21:10:07', '2025-05-25 21:10:09', 46, 46),
(23, 48, 43, '2025-06-08', '16:30:00', '16:50:00', 8, 'scheduled', 0, '', NULL, NULL, NULL, NULL, 2, '2025-05-25 21:18:49', '2025-05-25 21:18:49', 48, 48),
(24, 46, 43, '2025-06-08', '15:30:00', '15:50:00', 7, 'scheduled', 0, '', NULL, NULL, NULL, NULL, 2, '2025-05-26 11:24:42', '2025-05-26 11:24:42', 46, 46),
(25, 56, 43, '2025-06-01', '15:00:00', '15:20:00', 7, 'rescheduled', 1, '', NULL, NULL, NULL, NULL, 2, '2025-05-27 19:20:32', '2025-05-27 19:20:44', 56, 56);

-- --------------------------------------------------------

--
-- Table structure for table `appointment_followups`
--

CREATE TABLE `appointment_followups` (
  `followup_id` int(11) NOT NULL,
  `appointment_id` int(11) NOT NULL,
  `followup_status` enum('pending','contacted','resolved','ignored') NOT NULL DEFAULT 'pending',
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `updated_by` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `appointment_types`
--

CREATE TABLE `appointment_types` (
  `type_id` int(11) NOT NULL,
  `type_name` varchar(100) NOT NULL,
  `default_duration_minutes` int(11) NOT NULL DEFAULT 30,
  `description` text DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `appointment_types`
--

INSERT INTO `appointment_types` (`type_id`, `type_name`, `default_duration_minutes`, `description`, `is_active`, `created_at`, `updated_at`) VALUES
(7, 'Follow up', 20, NULL, 1, '2025-05-10 14:08:55', '2025-05-26 22:01:47'),
(8, 'Initial Visit', 20, NULL, 1, '2025-05-10 14:09:17', '2025-05-10 14:09:17');

-- --------------------------------------------------------

--
-- Table structure for table `audit_log`
--

CREATE TABLE `audit_log` (
  `log_id` int(11) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `action_type` varchar(50) NOT NULL,
  `target_table` varchar(100) DEFAULT NULL,
  `target_record_id` varchar(100) DEFAULT NULL,
  `action_details` text DEFAULT NULL,
  `performed_by_id` int(11) DEFAULT NULL,
  `performed_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `ip_address` varchar(45) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `audit_log`
--

INSERT INTO `audit_log` (`log_id`, `user_id`, `action_type`, `target_table`, `target_record_id`, `action_details`, `performed_by_id`, `performed_at`, `ip_address`) VALUES
(1, NULL, 'doctor_registration_rejected', 'pending_registrations', '2', 'Rejected doctor registration. Reason: . (Reg ID: 2, User: Adham@Doctor)', 42, '2025-05-09 19:59:29', NULL),
(2, 43, 'doctor_registration_approved', 'users', '43', 'Approved doctor registration; User account ACTIVATED (ID: 43). Doctor details updated. Documents linked: 0. (Reg ID: 2)', 42, '2025-05-09 20:00:04', NULL),
(3, 43, 'doctor_updated', 'users_doctors', '43', 'Doctor ID 43 updated. User rows: 1, Doctor rows: 1.', 42, '2025-05-09 20:18:29', NULL),
(4, 46, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-10 23:59:17', NULL),
(5, 46, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-10 23:59:37', NULL),
(6, 46, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-11 00:00:15', NULL),
(7, 46, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-11 00:01:57', NULL),
(8, 43, 'doctor_updated', 'users_doctors', '43', 'Doctor ID 43 updated. User rows: 1, Doctor rows: 1. Password changed.', 42, '2025-05-26 15:32:19', NULL),
(9, 43, 'doctor_updated', 'users_doctors', '43', 'Doctor ID 43 updated. User rows: 1, Doctor rows: 1. Password changed.', 42, '2025-05-26 15:38:52', NULL),
(10, 48, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-26 18:24:36', NULL),
(11, 48, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-26 18:25:04', NULL),
(12, 51, 'doctor_details_added', 'doctors', '51', 'Doctor details added/updated by admin (Step 2). Rows: 1. User account activated.', 42, '2025-05-26 18:30:17', NULL),
(13, 48, 'patient_updated', NULL, NULL, 'Patient profile updated by admin', 42, '2025-05-26 18:33:03', NULL),
(14, 51, 'doctor_updated', 'users_doctors', '51', 'Doctor ID 51 updated. User rows: 1, Doctor rows: 1.', 42, '2025-05-26 19:53:15', NULL),
(15, 43, 'doctor_updated', 'users_doctors', '43', 'Doctor ID 43 updated. User rows: 1, Doctor rows: 1.', 42, '2025-05-26 20:16:08', NULL),
(16, NULL, 'doctor_registration_rejected', 'pending_registrations', '3', 'Rejected doctor registration. Reason: sadasdas (Reg ID: 3, User: Nourhan@doctor)', 42, '2025-05-26 20:43:21', NULL),
(17, 54, 'doctor_registration_approved', 'users', '54', 'Approved doctor registration; User account ACTIVATED (ID: 54). Doctor details updated. (Reg ID: 3)', 42, '2025-05-26 20:48:36', NULL),
(18, 56, 'patient_updated', 'users', '56', 'Patient profile updated by admin', 42, '2025-05-26 21:47:55', NULL),
(19, 56, 'patient_updated', 'users', '56', 'Patient profile updated by admin', 42, '2025-05-26 21:48:06', NULL);

-- --------------------------------------------------------

--
-- Table structure for table `chats`
--

CREATE TABLE `chats` (
  `chat_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL,
  `start_time` timestamp NOT NULL DEFAULT current_timestamp(),
  `end_time` timestamp NULL DEFAULT NULL,
  `status` enum('active','closed','pending') DEFAULT 'active',
  `subject` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `chats`
--

INSERT INTO `chats` (`chat_id`, `patient_id`, `doctor_id`, `start_time`, `end_time`, `status`, `subject`, `created_at`, `updated_at`) VALUES
(1, 46, 43, '2025-05-13 19:35:24', NULL, 'active', 'following up on the Diagnose of Hypertension', '2025-05-13 19:35:24', '2025-05-26 15:46:17');

-- --------------------------------------------------------

--
-- Table structure for table `chat_messages`
--

CREATE TABLE `chat_messages` (
  `message_id` int(11) NOT NULL,
  `chat_id` int(11) NOT NULL,
  `sender_type` enum('doctor','patient','system') NOT NULL,
  `sender_id` int(11) NOT NULL,
  `message_text` text NOT NULL,
  `has_attachment` tinyint(1) DEFAULT 0,
  `sent_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `read_at` timestamp NULL DEFAULT NULL,
  `is_deleted` tinyint(1) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `chat_messages`
--

INSERT INTO `chat_messages` (`message_id`, `chat_id`, `sender_type`, `sender_id`, `message_text`, `has_attachment`, `sent_at`, `read_at`, `is_deleted`) VALUES
(1, 1, 'doctor', 43, 'hello', 0, '2025-05-13 20:14:36', '2025-05-25 20:39:59', 0),
(2, 1, 'patient', 46, 'hello', 0, '2025-05-13 20:23:38', '2025-05-13 20:23:44', 0),
(3, 1, 'doctor', 43, 'welcome', 0, '2025-05-13 20:23:52', '2025-05-25 20:39:59', 0),
(4, 1, 'doctor', 43, 'haiii', 0, '2025-05-13 20:46:26', '2025-05-25 20:39:59', 0),
(5, 1, 'patient', 46, 'hello', 0, '2025-05-13 20:47:15', '2025-05-13 20:47:18', 0),
(6, 1, 'doctor', 43, 'welcom to pro health care', 0, '2025-05-13 20:48:16', '2025-05-25 20:39:59', 0),
(7, 1, 'patient', 46, 'hello', 0, '2025-05-13 20:48:26', '2025-05-13 20:48:29', 0),
(8, 1, 'doctor', 43, 'hello', 0, '2025-05-24 20:02:04', '2025-05-25 20:39:59', 0),
(12, 1, 'patient', 46, 'hai', 0, '2025-05-25 20:40:01', '2025-05-26 11:32:29', 0),
(13, 1, 'patient', 46, 'wohooo', 0, '2025-05-25 20:40:06', '2025-05-26 11:32:29', 0),
(14, 1, 'patient', 46, 'haiiiiii', 0, '2025-05-26 15:46:17', '2025-05-26 15:47:20', 0);

-- --------------------------------------------------------

--
-- Table structure for table `conditions`
--

CREATE TABLE `conditions` (
  `condition_id` int(11) NOT NULL,
  `condition_name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `icd_code` varchar(20) DEFAULT NULL,
  `urgency_level` enum('low','medium','high','emergency') NOT NULL DEFAULT 'medium',
  `condition_type` enum('common','rare','chronic','acute') DEFAULT NULL,
  `age_relevance` varchar(100) DEFAULT NULL,
  `gender_relevance` enum('all','male','female') DEFAULT 'all',
  `specialist_type` varchar(100) DEFAULT NULL,
  `self_treatable` tinyint(1) DEFAULT 0,
  `typical_duration` varchar(100) DEFAULT NULL,
  `educational_content` text DEFAULT NULL,
  `overview` text DEFAULT NULL,
  `regular_symptoms_text` text DEFAULT NULL,
  `emergency_symptoms_text` text DEFAULT NULL,
  `risk_factors_text` text DEFAULT NULL,
  `treatment_protocols_text` text DEFAULT NULL,
  `symptoms_text` text DEFAULT NULL,
  `causes_text` text DEFAULT NULL,
  `complications_text` text DEFAULT NULL,
  `testing_details` text DEFAULT NULL,
  `diagnosis_details` text DEFAULT NULL,
  `condition_image_filename` varchar(500) DEFAULT NULL,
  `condition_video_filename` varchar(500) DEFAULT NULL,
  `testing_type_id` int(11) DEFAULT NULL,
  `diagnosis_type_id` int(11) DEFAULT NULL,
  `department_id` int(11) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `conditions`
--

INSERT INTO `conditions` (`condition_id`, `condition_name`, `description`, `icd_code`, `urgency_level`, `condition_type`, `age_relevance`, `gender_relevance`, `specialist_type`, `self_treatable`, `typical_duration`, `educational_content`, `overview`, `regular_symptoms_text`, `emergency_symptoms_text`, `risk_factors_text`, `treatment_protocols_text`, `symptoms_text`, `causes_text`, `complications_text`, `testing_details`, `diagnosis_details`, `condition_image_filename`, `condition_video_filename`, `testing_type_id`, `diagnosis_type_id`, `department_id`, `is_active`, `created_at`, `updated_at`) VALUES
(69, 'Common Cold', 'Viral infectious disease of the upper respiratory tract.', 'J00', 'low', 'acute', 'All ages', 'all', 'General Practitioner, Pediatrician', 1, '7-10 days', 'Rest, fluids, and over-the-counter medications can help manage symptoms. Antibiotics are not effective against viruses.', 'The common cold is a viral infection primarily affecting the nose and throat. It is typically harmless, although it might not feel that way.', NULL, 'Difficulty breathing or shortness of breath, persistent fever (over 101.3°F or 38.5°C), severe sore throat or headache, wheezing.', 'Weakened immune system, exposure to cold viruses, young age, crowded environments, smoking.', 'Symptomatic relief: decongestants, cough suppressants, pain relievers. Rest and hydration are key.', 'Runny or stuffy nose, sore throat, cough, congestion, slight body aches or a mild headache, sneezing, low-grade fever, generally feeling unwell (malaise).', 'Caused by rhinoviruses and other viruses transmitted through airborne droplets or direct contact.', 'Secondary infections like ear infections, sinusitis, or bronchitis, especially in vulnerable populations.', 'Usually diagnosed based on symptoms. Rapid strep test if severe sore throat to rule out strep throat.', 'Clinical diagnosis based on patient-reported symptoms and physical examination.', NULL, '', 1, 1, NULL, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(70, 'Influenza (Flu)', 'A contagious respiratory illness caused by influenza viruses.', 'J10', 'medium', 'acute', 'All ages, particularly risky for young children and elderly', 'all', 'General Practitioner, Infectious Disease Specialist', 0, '1-2 weeks', 'Annual vaccination is the best way to prevent the flu. Antiviral medications may be prescribed if caught early.', 'Influenza is a viral infection that attacks your respiratory system — your nose, throat and lungs. It can cause mild to severe illness.', NULL, 'Difficulty breathing, chest pain, sudden dizziness, confusion, severe or persistent vomiting, high fever unresponsive to medication.', 'Not vaccinated, chronic medical conditions (asthma, heart disease, diabetes), weakened immune system, age (young children and elderly).', 'Rest, fluids, antiviral drugs (e.g., oseltamivir, zanamivir) if prescribed by a doctor, especially for high-risk individuals.', 'Fever or feeling feverish/chills, cough, sore throat, runny or stuffy nose, muscle or body aches, headaches, fatigue (tiredness). Some people may have vomiting and diarrhea, though this is more common in children than adults.', 'Caused by influenza A, B, and C viruses. Spread mainly by droplets made when people with flu cough, sneeze or talk.', 'Pneumonia, bronchitis, sinus infections, ear infections, worsening of chronic medical conditions.', 'Rapid influenza diagnostic tests (RIDTs) can detect influenza antigens in respiratory specimens. PCR tests are more accurate.', 'Clinical symptoms often suggest flu, especially during flu season. Lab tests can confirm.', NULL, '', 1, 1, NULL, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(71, 'Hypertension (High Blood Pressure)', 'A common condition in which the long-term force of the blood against your artery walls is high enough that it may eventually cause health problems, such as heart disease.', 'I10', 'medium', 'chronic', 'More common in adults, risk increases with age', 'all', 'Cardiologist, General Practitioner', 0, 'Lifelong management', 'Lifestyle changes (diet, exercise, stress management) and medication are common treatments. Regular monitoring is crucial.', 'Hypertension is often called the \"silent killer\" because it usually has no warning signs or symptoms. Many people do not know they have it.', 'None', 'Severe chest pain, severe headache accompanied by confusion and blurred vision, nausea and vomiting, severe anxiety, shortness of breath, seizures, unresponsiveness.', 'Age, family history, obesity, not being physically active, tobacco use, too much salt (sodium) in your diet, too little potassium, drinking too much alcohol, stress, certain chronic conditions (kidney disease, diabetes, sleep apnea).', 'Lifestyle modifications (DASH diet, reduced sodium, regular exercise, weight loss, limit alcohol, quit smoking). Medications: diuretics, ACE inhibitors, ARBs, beta-blockers, calcium channel blockers.', 'Usually no symptoms. If blood pressure is extremely high (hypertensive crisis), symptoms can include severe headaches, shortness of breath, nosebleeds, anxiety.', 'Primary (essential) hypertension has no identifiable cause. Secondary hypertension is caused by an underlying condition (kidney problems, adrenal gland tumors, thyroid problems, certain medications).', 'Heart attack or stroke, aneurysm, heart failure, weakened and narrowed blood vessels in your kidneys, thickened, narrowed or torn blood vessels in the eyes, metabolic syndrome, trouble with memory or understanding.', 'Blood pressure measurement using a sphygmomanometer. May include blood tests, urine tests, ECG, echocardiogram to check for underlying causes or complications.', 'Diagnosis based on repeated blood pressure readings over time. Readings consistently 130/80 mmHg or higher.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-13 18:17:56', '2025-05-13 21:07:24'),
(72, 'Type 2 Diabetes Mellitus', 'A chronic condition that affects the way your body metabolizes sugar (glucose), your body\'s main source of fuel.', 'E11', 'medium', 'chronic', 'More common in adults over 45, but increasing in children and adolescents', 'all', 'Endocrinologist, General Practitioner', 0, 'Lifelong management', 'Management includes healthy eating, regular physical activity, blood sugar monitoring, and potentially diabetes medication or insulin therapy.', 'With type 2 diabetes, your body either resists the effects of insulin — a hormone that regulates the movement of sugar into your cells — or doesn\'t produce enough insulin to maintain normal glucose levels.', NULL, 'Hyperosmolar hyperglycemic state (HHS), diabetic ketoacidosis (DKA - less common than in Type 1 but possible), severe dehydration, loss of consciousness.', 'Overweight or obesity, inactivity, family history, race or ethnicity (e.g., African American, Hispanic, Native American, Asian American), age, prediabetes, gestational diabetes history, polycystic ovary syndrome.', 'Lifestyle changes (diet, exercise, weight loss). Oral medications (e.g., metformin, SGLT2 inhibitors, DPP-4 inhibitors, GLP-1 receptor agonists). Insulin therapy for some patients.', 'Increased thirst, frequent urination, increased hunger, unintended weight loss, fatigue, blurred vision, slow-healing sores, frequent infections, numbness or tingling in the hands or feet, areas of darkened skin (acanthosis nigricans).', 'A combination of genetic and lifestyle factors. Insulin resistance is a key feature, where cells don\'t respond effectively to insulin.', 'Heart and blood vessel disease, nerve damage (neuropathy), kidney damage (nephropathy), eye damage (retinopathy), foot damage, skin conditions, hearing impairment, Alzheimer\'s disease.', 'Fasting plasma glucose (FPG) test, A1C test, oral glucose tolerance test (OGTT).', 'Diagnosis based on blood sugar test results (e.g., A1C ≥6.5%, FPG ≥126 mg/dL, or 2-hour plasma glucose ≥200 mg/dL during OGTT).', NULL, '', 1, 1, 4, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(73, 'Asthma', 'A condition in which your airways narrow and swell and may produce extra mucus.', 'J45', 'medium', 'chronic', 'Can start at any age, common in childhood', 'all', 'Pulmonologist, Allergist, General Practitioner', 0, 'Lifelong, variable severity', 'Treatment involves avoiding triggers, using long-term control medications, and quick-relief inhalers for attacks. An asthma action plan is important.', 'Asthma can make breathing difficult and trigger coughing, a whistling sound (wheezing) when you breathe out and shortness of breath.', NULL, 'Severe and constant wheezing, coughing, or shortness of breath; trouble walking or talking; blue lips or fingernails (cyanosis); symptoms not relieved by quick-relief inhaler.', 'Family history, other allergic conditions (e.g., hay fever, eczema), being overweight, smoking or exposure to secondhand smoke, exposure to exhaust fumes or other types_of_pollution, occupational triggers (chemicals, dust).', 'Long-term control medications (e.g., inhaled corticosteroids, LABAs, leukotriene modifiers). Quick-relief (rescue) medications (e.g., short-acting beta-agonists). Identifying and avoiding triggers.', 'Shortness of breath, chest tightness or pain, wheezing when exhaling (common sign in children), trouble sleeping caused by shortness of breath, coughing or wheezing attacks that are worsened by a respiratory virus, such as a cold or the flu.', 'A combination of genetic and environmental factors. Triggers include allergens (pollen, dust mites, pet dander), respiratory infections, physical activity, cold air, air pollutants, certain medications, stress.', 'Symptoms that interfere with sleep, work or recreational activities; sick days from work or school; permanent narrowing of the bronchial tubes (airway remodeling); emergency room visits and hospitalizations for severe asthma attacks; side effects from long-term use of some medications used to stabilize severe asthma.', 'Lung function tests (spirometry, peak flow), methacholine challenge, allergy testing.', 'Based on medical history, physical exam, and lung function tests.', NULL, '', 3, 1, 3, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(74, 'Migraine', 'A type of headache that can cause severe throbbing pain or a pulsing sensation, usually on one side of the head.', 'G43', 'medium', 'chronic', 'Can begin in childhood, adolescence or early adulthood. More common in women.', 'female', 'Neurologist, Headache Specialist', 0, 'Episodic or chronic throughout life', 'Treatment focuses on relieving symptoms (abortive) and preventing future attacks (preventive). Identifying triggers is important.', 'Migraine is often accompanied by nausea, vomiting, and extreme sensitivity to light and sound. Migraine attacks can last for hours to days, and the pain can be so severe that it interferes with your daily activities.', NULL, 'Sudden, severe headache (\"thunderclap headache\"); headache with fever, stiff neck, mental confusion, seizures, double vision, weakness, numbness or trouble speaking; headache after a head injury, especially if the headache gets worse.', 'Family history, age, hormonal changes in women (estrogen fluctuations), stress, certain foods and food additives (aged cheeses, salty foods, processed foods, MSG, caffeine, alcohol - especially red wine), changes in sleep patterns, intense physical exertion, changes in the environment (weather, barometric pressure), medications (e.g., oral contraceptives, vasodilators).', 'Pain-relieving medications (NSAIDs, triptans, CGRP antagonists). Preventive medications (beta-blockers, antidepressants, anti-seizure drugs, CGRP monoclonal antibodies, Botox injections). Lifestyle adjustments (regular sleep, stress management, trigger avoidance).', 'Moderate to severe pulsating or throbbing pain, usually on one side of the head; pain worsened by physical activity; nausea, vomiting; sensitivity to light (photophobia), sound (phonophobia), and sometimes smells; aura (visual disturbances, tingling, weakness, speech problems) may precede or accompany headache.', 'Exact cause unknown, but genetics and environmental factors appear to play a role. Thought to involve changes in the brainstem and its interactions with the trigeminal nerve pathway. Imbalances in brain chemicals, including serotonin, may be involved.', 'Status migrainosus (migraine attack lasting >72 hours), migrainous infarction (stroke associated with migraine aura - rare), chronic migraine (15 or more headache days per month for >3 months).', 'Medical history, neurological examination. Imaging tests (CT, MRI) may be done to rule out other causes if headache is complex or atypical.', 'Clinical diagnosis based on headache characteristics, associated symptoms, and family history, after ruling out other causes.', NULL, '', 2, 1, 18, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(75, 'Atopic Dermatitis (Eczema)', 'A condition that makes your skin red and itchy. It\'s common in children but can occur at any age.', 'L20', 'low', 'chronic', 'Common in infants and children, can persist into adulthood or start in adulthood.', 'all', 'Dermatologist, Allergist', 0, 'Chronic, with flare-ups and remissions', 'Treatment aims to relieve itching and inflammation, heal the skin, and prevent flare-ups. Moisturizing regularly is key.', 'Atopic dermatitis is long lasting (chronic) and tends to flare periodically. It may be accompanied by asthma or hay fever.', 'None', 'Widespread skin infection (oozing, pus, yellow crusts, fever), rapidly worsening rash, signs of anaphylaxis if related to food allergy.', 'Personal or family history of eczema, allergies, hay fever or asthma; age (more common in children); environmental factors (irritants, allergens, climate).', 'Moisturizers, topical corticosteroids, topical calcineurin inhibitors, antihistamines for itching, wet wrap therapy, light therapy (phototherapy), systemic corticosteroids or immunosuppressants for severe cases. Avoid known triggers and irritants.', 'Dry skin; itching, which may be severe, especially at night; red to brownish-gray patches, especially on the hands, feet, ankles, wrists, neck, upper chest, eyelids, inside the bend of the elbows and knees, and in infants, the face and scalp; small, raised bumps, which may leak fluid and crust over when scratched; thickened, cracked, scaly skin; raw, sensitive, swollen skin from scratching.', 'A combination of genetic factors (e.g., filaggrin gene mutation affecting skin barrier function) and immune system dysfunction, along with environmental triggers.', 'Skin infections (bacterial, viral), neurodermatitis (itch-scratch cycle leading to thickened skin), eye complications (e.g., conjunctivitis, keratitis), allergic contact dermatitis, irritant hand dermatitis, sleep problems.', 'Usually diagnosed based on skin examination and medical history. Allergy testing (skin prick, patch test) may be done if specific triggers are suspected.', 'Clinical diagnosis based on appearance of the rash, itching, and history of flare-ups.', NULL, 'uploads/condition_videos/20250521135307512973_71458eabd6e429a8eecdafb78f2d404a_t3.mp4', NULL, NULL, 20, 1, '2025-05-13 18:17:56', '2025-05-21 10:53:07'),
(76, 'Gastroesophageal Reflux Disease (GERD)', 'A chronic digestive disease that occurs when stomach acid or, occasionally, stomach content, flows back into your food pipe (esophagus).', 'K21', 'low', 'chronic', 'All ages, common in adults', 'all', 'Gastroenterologist, General Practitioner', 0, 'Chronic, requires management', 'Lifestyle changes and over-the-counter medications are often the first line of treatment. Prescription medications or surgery may be needed for more severe cases.', 'The backwash (reflux) irritates the lining of your esophagus and causes GERD.', NULL, 'Severe chest pain (especially if radiating to arm/jaw, to rule out heart attack), persistent vomiting, vomiting blood, black or tarry stools, unintentional weight loss, choking.', 'Obesity, hiatal hernia, pregnancy, smoking, dry mouth, asthma, diabetes, delayed stomach emptying, connective tissue disorders (e.g., scleroderma). Certain foods and drinks (fatty/fried foods, tomato sauce, alcohol, chocolate, mint, garlic, onion, caffeine).', 'Lifestyle: Avoid trigger foods, eat smaller meals, don\'t lie down after eating, elevate head of bed, lose weight if overweight, quit smoking. Medications: Antacids, H2-receptor blockers (e.g., famotidine), proton pump inhibitors (PPIs, e.g., omeprazole, lansoprazole). Surgery in severe cases (e.g., fundoplication).', 'A burning sensation in your chest (heartburn), usually after eating, which might be worse at night or when lying down; chest pain; difficulty swallowing (dysphagia); regurgitation of food or sour liquid; sensation of a lump in your throat. If GERD occurs at night: chronic cough, laryngitis, new or worsening asthma, disrupted sleep.', 'Frequent acid reflux. The lower esophageal sphincter (LES), a muscular ring between the esophagus and stomach, relaxes abnormally or weakens.', 'Esophagitis (inflammation of the esophagus), esophageal stricture (narrowing), Barrett\'s esophagus (precancerous changes), esophageal cancer (rare), respiratory problems.', 'Endoscopy, ambulatory acid (pH) probe test, esophageal manometry, X-ray of upper digestive system.', 'Based on symptoms, response to treatment, or diagnostic tests.', NULL, '', 5, 1, 5, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(77, 'Anxiety Disorder, Generalized (GAD)', 'Characterized by persistent and excessive worry about a number of different things.', 'F41.1', 'medium', 'chronic', 'Can begin at any point in life, average onset around 30', 'all', 'Psychiatrist, Psychologist, Therapist, General Practitioner', 0, 'Can be chronic, treatable', 'Treatment often involves psychotherapy (talk therapy), medication, or a combination. Lifestyle changes and stress management techniques can also help.', 'People with GAD may anticipate disaster and may be overly concerned about money, health, family, work, or other issues. Individuals with GAD find it difficult to control their worry.', NULL, 'Suicidal thoughts or behaviors, panic attacks that are severe or frequent, inability to function in daily life due to anxiety.', 'Family history of anxiety, traumatic experiences, chronic physical illness, stress buildup, personality factors (e.g., timid, negative outlook), other mental health disorders (e.g., depression).', 'Psychotherapy (Cognitive Behavioral Therapy - CBT is highly effective). Medications: SSRIs, SNRIs, buspirone, benzodiazepines (short-term). Relaxation techniques, mindfulness, regular exercise, adequate sleep, avoiding caffeine and illicit drugs.', 'Persistent worrying or anxiety about a number of areas that are out of proportion to the impact of the events; overthinking plans and solutions to all possible worst-case outcomes; perceiving situations and events as threatening, even when they aren\'t; difficulty handling uncertainty; indecisiveness and fear of making the wrong decision; inability to set aside or let go of a worry; inability to relax, feeling restless, and feeling keyed up or on edge; difficulty concentrating, or the feeling that your mind \"goes blank\"; fatigue; trouble sleeping; muscle tension or muscle aches; trembling, feeling twitchy; nervousness or being easily startled; sweating; nausea, diarrhea or irritable bowel syndrome; irritability.', 'Complex interaction of biological factors (brain chemistry, genetics), personality, and life experiences.', 'Depression, substance abuse, sleep problems, digestive or bowel problems, headaches and chronic pain, social isolation, problems functioning at school or work, poor quality of life.', 'Psychological evaluation by a mental health professional. Medical evaluation to rule out physical conditions that may cause similar symptoms.', 'Diagnosis based on DSM-5 criteria, including excessive anxiety and worry occurring more days than not for at least 6 months about a number of events or activities, and difficulty controlling the worry, along with associated physical symptoms.', NULL, '', NULL, 1, NULL, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(78, 'Iron Deficiency Anemia', 'A common type of anemia — a condition in which blood lacks adequate healthy red blood cells.', 'D50', 'low', 'acute', 'All ages, common in women of childbearing age, infants, and elderly.', 'all', 'General Practitioner, Hematologist', 0, 'Varies, treatable with iron supplementation', 'Treatment involves iron supplements and addressing the underlying cause of iron deficiency.', 'Iron deficiency anemia is due to insufficient iron. Without enough iron, your body can\'t produce enough of a substance in red blood cells that enables them to carry oxygen (hemoglobin).', NULL, 'Severe shortness of breath or chest pain, fainting, signs of significant blood loss.', 'Blood loss (heavy menstrual periods, internal bleeding from ulcers or colon cancer), lack of iron in diet, inability to absorb iron (e.g., celiac disease, intestinal surgery), pregnancy.', 'Iron supplements (oral or intravenous). Dietary changes to include more iron-rich foods (red meat, poultry, fish, beans, lentils, iron-fortified cereals, dark green leafy vegetables). Treating the underlying cause of blood loss or poor absorption.', 'Extreme fatigue, weakness, pale skin, chest pain, fast heartbeat or shortness of breath, headache, dizziness or lightheadedness, cold hands and feet, inflammation or soreness of your tongue, brittle nails, unusual cravings for non-nutritive substances (pica), poor appetite (especially in infants and children).', 'Depletion of iron stores in the body, leading to reduced hemoglobin production.', 'Heart problems (rapid or irregular heartbeat, enlarged heart, heart failure), problems during pregnancy (premature birth, low birth weight), growth problems in infants and children, increased susceptibility to infections.', 'Complete blood count (CBC) to check hemoglobin and hematocrit levels, red blood cell size and color. Tests for iron levels (serum iron, ferritin, transferrin saturation). Tests to find source of bleeding if suspected (e.g., endoscopy, colonoscopy).', 'Based on blood tests showing low hemoglobin, hematocrit, and iron stores.', NULL, '', 1, 1, NULL, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(79, 'Osteoarthritis', 'The most common form of arthritis, affecting millions of people worldwide. It occurs when the protective cartilage that cushions the ends of your bones wears down over time.', 'M15-M19', 'low', 'chronic', 'Increases with age, common over 50', 'all', 'Rheumatologist, Orthopedist, General Practitioner', 0, 'Lifelong, progressive', 'Treatment focuses on relieving pain and improving joint function. Includes lifestyle changes, physical therapy, medications, and sometimes surgery.', 'Osteoarthritis most commonly affects joints in your hands, knees, hips and spine. Symptoms can usually be managed, although the damage to joints can\'t be reversed.', NULL, 'Sudden inability to bear weight on a joint, severe pain and swelling, signs of infection (fever, redness, warmth).', 'Older age, sex (women are more likely to develop osteoarthritis), obesity, joint injuries, repeated stress on the joint, genetics, bone deformities, certain metabolic diseases (like diabetes and hemochromatosis).', 'Pain relievers (acetaminophen, NSAIDs), physical therapy, occupational therapy, assistive devices, weight loss, intra-articular injections (corticosteroids, hyaluronic acid), joint replacement surgery in severe cases.', 'Pain in affected joints during or after movement, stiffness (especially in the morning or after inactivity), tenderness, loss of flexibility, grating sensation (crepitus), bone spurs.', 'Breakdown of cartilage, the slippery tissue that covers the ends of bones in a joint, allowing nearly frictionless joint motion.', 'Chronic pain, disability, reduced quality of life, depression, sleep disturbances.', 'X-rays can show cartilage loss, bone spurs, and narrowing of joint space. MRI may be used for more detailed images. Joint fluid analysis can rule out other conditions like gout or infection.', 'Based on symptoms, physical examination, and imaging tests (X-rays).', NULL, '', 2, 1, 19, 1, '2025-05-13 18:17:56', '2025-05-13 18:17:56'),
(80, 'Acne', 'A widespread skin condition where hair follicles become blocked, causing pimples, whiteheads, blackheads, and cysts.', 'D202', 'low', 'common', 'all', 'all', 'Dermatologist, Allergist', 0, 'Noneewjrgnljenwrg', 'Noneerjgnlwenkgr', 'is a common skin condition where pores become clogged with oil, dead skin cells, and bacteria, leading to pimples, blackheads, and whiteheads', 'Blackheads , Whiteheads ,Pimples , Cysts.', 'Spreading redness and fever.\r\nLarge, spreading red area.\r\nSwelling of the face, lips, tongue, or eyes.', 'Nonewerljfgnlwejrng', 'lekrwjfgnlenwrgklNone', NULL, 'Noneqwejfnlwqnrjfl;wnef', 'Noneelrnfgl;wenr;lgferw', 'erlfgnlwenrgewNone', 'ljenrgljnewljrg', 'uploads/condition_images/20250524221639116758_Acne.jpeg', NULL, NULL, NULL, 20, 1, '2025-05-24 19:16:39', '2025-05-24 19:18:33'),
(84, 'Coronary Artery Disease (CAD)', 'Damage or disease in the heart\'s major blood vessels, usually caused by plaque buildup (atherosclerosis).', 'I25.10', 'high', 'chronic', 'Primarily Older Adults', 'all', 'Cardiologist', 0, 'Lifelong', NULL, 'Overview of CAD, focusing on atherosclerosis and its consequences for heart function.', 'Chest pain (angina), shortness of breath, fatigue, especially during exertion.', 'Sudden severe chest pain/pressure, pain radiating to arm/jaw, shortness of breath, sweating, nausea - indicates possible heart attack, seek emergency care.', 'High cholesterol, high blood pressure, smoking, diabetes, obesity, family history, physical inactivity.', 'Lifestyle changes, medications (statins, aspirin, beta-blockers), angioplasty, stenting, bypass surgery.', 'Chest pain (angina), shortness of breath, fatigue, palpitations.', 'Atherosclerosis (buildup of cholesterol plaques in arteries), inflammation.', 'Heart attack, heart failure, arrhythmia, stroke.', 'ECG, stress test, echocardiogram, coronary angiography, CT coronary angiogram.', 'Diagnosis based on symptoms, risk factors, and results of cardiac tests.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 11:46:09', '2025-05-30 11:46:09'),
(85, 'Atrial Fibrillation (AFib)', 'An irregular and often rapid heart rate that can increase your risk of stroke, heart failure and other heart-related complications.', 'I48.91', 'medium', 'chronic', 'More common in older adults', 'all', 'Cardiologist / Electrophysiologist', 0, 'Lifelong or episodic', NULL, 'Overview of AFib, its types, and risks, particularly stroke.', 'Palpitations, fatigue, dizziness, shortness of breath, chest pain.', 'Stroke symptoms (FAST: Face drooping, Arm weakness, Speech difficulty, Time to call 911), severe chest pain, fainting.', 'Age, heart disease, high blood pressure, obesity, diabetes, sleep apnea, excessive alcohol intake.', 'Rate control medications, rhythm control medications, anticoagulants, catheter ablation, pacemaker.', 'Irregular heartbeat, palpitations, fatigue, shortness of breath, dizziness.', 'Abnormal electrical impulses in the atria of the heart.', 'Stroke, heart failure, blood clots.', 'ECG, Holter monitor, event monitor, echocardiogram, stress test.', 'Diagnosis confirmed by ECG showing characteristic irregular rhythm.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 11:46:09', '2025-05-30 11:46:09'),
(89, 'Heart Failure (CHF)', 'Heart muscle doesn\'t pump blood as well as it should.', 'I50.9', 'high', 'chronic', 'Older Adults', 'all', 'Cardiologist', 0, 'Lifelong', 'None', 'Overview of Heart Failure, types and stages.', 'Shortness of breath, fatigue, swelling in legs/ankles/feet (edema), rapid or irregular heartbeat.', 'Sudden severe shortness of breath, chest pain, coughing up pink/foamy mucus, fainting.', 'CAD, HBP, diabetes, obesity, past heart attack.', 'Medications (ACE inhibitors, beta-blockers, diuretics), lifestyle changes, pacemakers, surgery.', 'Dyspnea, edema, fatigue.', 'Damage to heart muscle.', 'Kidney damage, liver damage, arrhythmias.', 'Echocardiogram, ECG, chest X-ray, blood tests (BNP).', 'Clinical symptoms, imaging, blood tests.', 'uploads/condition_images/20250530154816518686_heartfailure.png', NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:48:16'),
(90, 'Arrhythmia (General)', 'Abnormal heart rhythm (too fast, too slow, or irregular).', 'I49.9', 'medium', 'acute', 'All ages', 'all', 'Cardiologist/Electrophysiologist', 0, 'Variable', 'None', 'Overview of various heart rhythm disorders.', 'Palpitations, dizziness, fainting (syncope), shortness of breath, chest discomfort.', 'Prolonged palpitations with chest pain or fainting, signs of stroke.', 'Heart disease, electrolyte imbalance, stress, medications.', 'Medications, pacemakers, ICDs, ablation.', 'Palpitations, syncope.', 'Electrical system issues.', 'Stroke, heart failure, sudden cardiac arrest.', 'ECG, Holter monitor, event recorder, electrophysiology study.', 'ECG interpretation, clinical context.', 'uploads/condition_images/20250530154358853478_arrhythmia.gif', NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:43:58'),
(91, 'Valvular Heart Disease', 'Damage or defect in one of the four heart valves.', 'I35.0', 'medium', 'chronic', 'All ages, more common with age', 'all', 'Cardiologist', 0, 'Lifelong/Progressive', NULL, 'Overview of diseases affecting heart valves (stenosis, regurgitation).', 'Shortness of breath, fatigue, chest pain, irregular heartbeat, dizziness, fainting, swollen ankles/feet.', 'Sudden severe shortness of breath, chest pain, loss of consciousness.', 'Congenital defects, infections (rheumatic fever), aging, CAD.', 'Medications, valve repair or replacement surgery.', 'Dyspnea, murmur, fatigue.', 'Valve damage/deformity.', 'Heart failure, blood clots, endocarditis.', 'Echocardiogram, ECG, chest X-ray, cardiac catheterization.', 'Echocardiogram is key diagnostic tool.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(92, 'Peripheral Artery Disease (PAD)', 'Narrowed arteries reduce blood flow to limbs, usually legs.', 'I73.9', 'medium', 'chronic', 'Older Adults, smokers', 'all', 'Vascular Surgeon/Cardiologist', 0, 'Lifelong/Progressive', NULL, 'Overview of PAD and its impact on limb circulation.', 'Painful cramping in hip, thigh or calf muscles after activity (claudication), leg numbness/weakness, coldness in lower leg/foot, sores that won\'t heal.', 'Sudden loss of circulation to a limb (acute limb ischemia) - severe pain, coldness, pallor, pulselessness.', 'Smoking, diabetes, obesity, HBP, high cholesterol, age.', 'Lifestyle changes, medications (antiplatelets, statins), angioplasty, stenting, bypass surgery.', 'Claudication, rest pain.', 'Atherosclerosis in peripheral arteries.', 'Critical limb ischemia, amputation, increased risk of heart attack/stroke.', 'Ankle-Brachial Index (ABI), ultrasound, angiography.', 'ABI, imaging studies.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(93, 'Myocardial Infarction (Heart Attack)', 'Blockage of blood flow to a part of the heart muscle.', 'I21.9', 'emergency', 'acute', 'Adults, esp. older', 'all', 'Cardiologist/ER Physician', 0, 'Acute event, long-term management', NULL, 'Overview of heart attack, causes, and immediate actions.', 'Chest pain/pressure (angina), pain radiating to arm/jaw/back, shortness of breath, sweating, nausea, dizziness.', 'Symptoms are the emergency; call emergency services immediately.', 'CAD, smoking, HBP, diabetes, high cholesterol, family history.', 'Emergency reperfusion (PCI, thrombolytics), long-term medications (aspirin, beta-blockers, statins).', 'Severe chest pain, dyspnea.', 'Coronary artery thrombosis.', 'Heart failure, arrhythmias, cardiac arrest.', 'ECG, cardiac enzymes (troponin), echocardiogram, coronary angiography.', 'ECG changes, elevated cardiac markers.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(94, 'Hyperlipidemia (High Cholesterol)', 'High levels of lipids (fats), including cholesterol and triglycerides, in the blood.', 'E78.5', 'low', 'chronic', 'Adults', 'all', 'Primary Care/Cardiologist', 0, 'Lifelong', NULL, 'Overview of high cholesterol and its link to heart disease.', 'Usually asymptomatic. Detected by blood test.', 'No direct emergency symptoms; risk factor for emergencies like heart attack/stroke.', 'Diet high in saturated/trans fats, obesity, lack of exercise, smoking, genetics, age.', 'Lifestyle changes (diet, exercise), statins and other lipid-lowering medications.', 'Asymptomatic.', 'Diet, genetics, lifestyle.', 'Atherosclerosis, CAD, stroke, PAD.', 'Lipid panel (blood test).', 'Blood test results.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(95, 'Cardiomyopathy', 'Disease of the heart muscle making it harder for the heart to pump blood.', 'I42.9', 'medium', 'chronic', 'All ages', 'all', 'Cardiologist', 0, 'Lifelong', NULL, 'Overview of different types of cardiomyopathy.', 'Shortness of breath, fatigue, swelling of legs/ankles/feet, dizziness, palpitations, chest pain.', 'Severe shortness of breath, fainting, signs of heart failure worsening rapidly.', 'Genetics, HBP, past heart attack, viral infections, alcohol abuse, diabetes.', 'Medications, implantable devices (pacemaker, ICD), heart transplant in severe cases.', 'Dyspnea, edema, fatigue.', 'Various causes affecting heart muscle.', 'Heart failure, arrhythmias, blood clots, sudden cardiac death.', 'Echocardiogram, MRI, ECG, genetic testing.', 'Echocardiogram is primary diagnostic tool.', NULL, NULL, NULL, NULL, 17, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(99, 'Alzheimer\'s Disease', 'Progressive neurologic disorder causing brain cells to die.', 'G30.9', 'high', 'chronic', 'Older adults (65+)', 'all', 'Neurologist', 0, 'Progressive, lifelong', NULL, 'Overview of Alzheimer\'s.', 'Memory loss, confusion, difficulty planning.', 'Sudden worsening confusion, agitation.', 'Age, genetics, CVD.', 'Symptomatic meds, support.', 'Memory loss, confusion.', 'Amyloid plaques, tau tangles.', 'Loss of independence.', 'Cognitive tests, MRI/CT.', 'Clinical assessment, exclusion.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(100, 'Parkinson\'s Disease', 'Progressive nervous system disorder affecting movement.', 'G20', 'medium', 'chronic', 'Usually after age 60', 'male', 'Neurologist', 0, 'Progressive, lifelong', NULL, 'Overview of Parkinson\'s.', 'Tremor, bradykinesia, rigidity.', 'Sudden falls, severe swallowing issues.', 'Age, genetics, toxins.', 'Levodopa, DBS, therapy.', 'Tremor, slowness, stiffness.', 'Loss of dopamine neurons.', 'Movement issues, dementia.', 'Clinical diagnosis, neurological exam.', 'Motor symptoms, response to meds.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(101, 'Epilepsy (Seizure Disorder)', 'Neurological disorder marked by recurrent, unprovoked seizures.', 'G40.9', 'medium', 'chronic', 'All ages', 'all', 'Neurologist', 0, 'Lifelong, can remit', NULL, 'Overview of epilepsy and seizure types.', 'Recurrent seizures (convulsive or non-convulsive), temporary confusion, staring spells, loss of consciousness or awareness.', 'Status epilepticus (seizure lasting >5 mins or multiple seizures without recovery), seizure with injury or breathing difficulty.', 'Genetics, head trauma, stroke, brain tumors, infections.', 'Anti-epileptic drugs (AEDs), surgery, vagus nerve stimulation, ketogenic diet.', 'Seizures, aura.', 'Abnormal brain electrical activity.', 'Injury during seizure, cognitive issues, SUDEP.', 'EEG, MRI, CT scan, video-EEG monitoring.', 'Clinical history, EEG findings.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(102, 'Stroke (Cerebrovascular Accident - CVA)', 'Damage to the brain from interruption of its blood supply.', 'I63.9', 'emergency', 'acute', 'Older Adults, HBP/AFib patients', 'all', 'Neurologist/ER Physician', 0, 'Acute event, long-term rehab', NULL, 'Overview of ischemic and hemorrhagic stroke.', 'Sudden numbness/weakness (face, arm, leg, often one side), confusion, trouble speaking/understanding, vision problems, dizziness, severe headache.', 'Symptoms are the emergency (FAST: Face, Arms, Speech, Time). Call emergency services immediately.', 'HBP, smoking, diabetes, AFib, high cholesterol, family history.', 'Thrombolytics (tPA for ischemic), mechanical thrombectomy, supportive care, rehabilitation.', 'Sudden neurological deficits.', 'Ischemia or hemorrhage.', 'Permanent disability, death, cognitive impairment.', 'CT scan, MRI, angiography, carotid ultrasound.', 'Rapid imaging, neurological exam.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(103, 'Multiple Sclerosis (MS)', 'Autoimmune disease affecting brain and spinal cord (central nervous system).', 'G35', 'medium', 'chronic', 'Young adults (20-40)', 'female', 'Neurologist', 0, 'Lifelong, variable course', NULL, 'Overview of MS types and management.', 'Fatigue, numbness/tingling, weakness, vision problems (optic neuritis), dizziness, balance problems, bladder/bowel issues, cognitive changes.', 'Sudden severe relapse, rapid progression of disability, severe infection.', 'Genetics, environmental factors (low vitamin D, certain viral infections like EBV), smoking.', 'Disease-modifying therapies (DMTs), symptom management, physical therapy.', 'Fatigue, weakness, vision issues.', 'Immune system attacks myelin.', 'Disability, cognitive decline.', 'MRI, evoked potentials, lumbar puncture (CSF analysis).', 'McDonald criteria (clinical and MRI findings).', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(104, 'Amyotrophic Lateral Sclerosis (ALS)', 'Progressive neurodegenerative disease affecting nerve cells in brain and spinal cord controlling voluntary muscles.', 'G12.21', 'high', 'chronic', 'Adults (40-70)', 'male', 'Neurologist', 0, 'Rapidly progressive, fatal', NULL, 'Overview of ALS, also known as Lou Gehrig\'s disease.', 'Muscle weakness/twitching (often starting in limbs), slurred speech, difficulty swallowing/breathing, muscle cramps, fatigue.', 'Respiratory failure, aspiration pneumonia.', 'Mostly sporadic; some familial cases (genetic mutations).', 'Riluzole, edaravone, supportive care (respiratory, nutritional, mobility).', 'Muscle weakness, dysarthria, dysphagia.', 'Degeneration of motor neurons.', 'Respiratory failure, paralysis.', 'EMG, nerve conduction studies, MRI (to rule out others).', 'Clinical exam, EMG, exclusion of other diseases.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(105, 'Peripheral Neuropathy', 'Damage to peripheral nerves, often causing weakness, numbness, and pain, usually in hands and feet.', 'G62.9', 'medium', 'chronic', 'Varies by cause', 'all', 'Neurologist', 0, 'Often chronic, can improve', NULL, 'Overview of causes and symptoms of peripheral neuropathy.', 'Gradual onset of numbness, prickling or tingling in feet/hands, sharp/jabbing/throbbing/burning pain, muscle weakness, lack of coordination, sensitivity to touch.', 'Sudden severe weakness, rapid progression, signs of autonomic neuropathy (e.g., severe dizziness).', 'Diabetes (most common), injuries, infections, toxins, vitamin deficiencies, autoimmune diseases, alcohol abuse.', 'Treat underlying cause, pain medications, physical therapy.', 'Numbness, pain, weakness in extremities.', 'Nerve damage from various causes.', 'Falls, foot ulcers, chronic pain.', 'Nerve conduction studies, EMG, blood tests, nerve biopsy (rarely).', 'Clinical exam, nerve tests, identifying cause.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(106, 'Tension Headache', 'Mild to moderate pain often described as feeling like a tight band around the head.', 'G44.2', 'low', 'common', 'All ages, very common', 'all', 'Primary Care/Neurologist', 1, 'Minutes to days/episode', NULL, 'Overview of tension-type headaches.', 'Dull, aching head pain; sensation of tightness or pressure across forehead or on sides/back of head; scalp tenderness.', 'Rarely an emergency unless severe and atypical, or with other neurological symptoms.', 'Stress, muscle tension, poor posture, fatigue, dehydration, caffeine withdrawal.', 'OTC pain relievers, stress management, relaxation techniques, physical therapy.', 'Dull ache, head pressure.', 'Muscle contraction, stress.', 'Chronic tension headaches.', 'Clinical diagnosis based on history.', 'Based on headache characteristics.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(107, 'Meningitis', 'Inflammation of the membranes (meninges) surrounding brain and spinal cord, usually due to infection.', 'G03.9', 'emergency', 'acute', 'All ages, esp. young/old/immunocompromised', 'all', 'ER Physician/Infectious Disease/Neurologist', 0, 'Acute, potentially severe', NULL, 'Overview of viral and bacterial meningitis.', 'Sudden high fever, severe headache, stiff neck, nausea/vomiting, confusion, sensitivity to light, rash (in some types).', 'Symptoms are the emergency. Rapid progression can be life-threatening.', 'Bacterial, viral, or fungal infection.', 'Antibiotics (for bacterial), antiviral (for some viral), supportive care. Bacterial meningitis is a medical emergency.', 'Fever, headache, stiff neck.', 'Infection of meninges.', 'Brain damage, hearing loss, seizures, death.', 'Lumbar puncture (spinal tap), blood cultures, CT/MRI.', 'CSF analysis from lumbar puncture.', NULL, NULL, NULL, NULL, 18, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(109, 'Low Back Pain', 'Pain in the lumbosacral area of the spine.', 'M54.5', 'low', 'common', 'All ages, adults', 'all', 'Orthopedist/PT', 1, 'Acute or Chronic', NULL, 'Overview of Low Back Pain.', 'Dull or sharp back pain, stiffness.', 'New bowel/bladder issues, leg weakness.', 'Strain, disc issues, poor posture.', 'Rest, PT, pain relief.', 'Back ache, stiffness.', 'Muscle strain, disc problems.', 'Chronic pain, nerve issues.', 'Physical exam, X-ray, MRI.', 'Clinical diagnosis, imaging if needed.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(110, 'Carpal Tunnel Syndrome', 'Median nerve compression at the wrist.', 'G56.00', 'medium', 'common', 'Adults, women', 'female', 'Orthopedist/Hand Surgeon', 0, 'Variable, can be chronic', NULL, 'Overview of Carpal Tunnel.', 'Numbness, tingling, weakness in hand.', 'Sudden loss of hand function.', 'Repetitive motion, injury.', 'Splinting, injections, surgery.', 'Hand numbness, pain.', 'Median nerve compression.', 'Nerve damage, muscle atrophy.', 'NCS, EMG.', 'Symptoms, exam, nerve tests.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(111, 'Rheumatoid Arthritis (RA)', 'Autoimmune disease causing chronic inflammation of joints.', 'M06.9', 'medium', 'chronic', 'Adults, any age', 'female', 'Rheumatologist/Orthopedist', 0, 'Lifelong, progressive', NULL, 'Overview of RA and its systemic effects.', 'Tender, warm, swollen joints (often symmetrical); joint stiffness (worse in mornings); fatigue, fever, weight loss.', 'Sudden severe joint flare, signs of systemic complications (e.g., vasculitis).', 'Genetics, smoking, environmental factors.', 'DMARDs, biologics, NSAIDs, corticosteroids, physical therapy, surgery for joint damage.', 'Joint pain, swelling, stiffness.', 'Autoimmune attack on synovium.', 'Joint deformity, disability, systemic inflammation.', 'Blood tests (RF, anti-CCP), X-rays, MRI.', 'Clinical criteria, blood tests, imaging.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(112, 'Bone Fracture', 'A break in the continuity of a bone.', 'S00-T88 (varies by l', 'high', 'acute', 'All ages', 'all', 'Orthopedist/ER Physician', 0, 'Weeks to months for healing', NULL, 'Overview of different types of bone fractures.', 'Pain, swelling, bruising, deformity, inability to use affected limb or bear weight.', 'Open fracture (bone pierces skin), signs of nerve/vascular damage (numbness, pallor, pulselessness), multiple fractures.', 'Trauma (falls, accidents), osteoporosis, stress/overuse injuries.', 'Immobilization (cast, splint), reduction (setting the bone), surgery (pins, plates, rods), pain management.', 'Pain, swelling, deformity.', 'Trauma, stress, pathology.', 'Malunion, nonunion, infection, compartment syndrome.', 'X-ray, CT scan, MRI (for stress fractures or soft tissue).', 'X-ray is primary diagnostic tool.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(113, 'Tendonitis', 'Inflammation or irritation of a tendon.', 'M77.9', 'low', 'common', 'All ages, esp. active individuals', 'all', 'Orthopedist/Sports Medicine/PT', 1, 'Days to weeks, can be chronic', NULL, 'Overview of tendonitis in various locations (e.g., Achilles, rotator cuff, tennis elbow).', 'Dull ache or pain at the site of the tendon, tenderness, mild swelling, pain with movement of the affected area.', 'Sudden inability to move a joint, severe pain, suspected tendon rupture.', 'Repetitive motion, overuse, sudden injury, aging, improper technique in sports.', 'Rest, ice, compression, elevation (RICE); NSAIDs, physical therapy, corticosteroid injections (used cautiously), eccentric exercises.', 'Localized pain, tenderness.', 'Overuse, microtrauma.', 'Chronic pain, tendon rupture.', 'Clinical exam, ultrasound, MRI (if severe or chronic).', 'Physical exam, patient history.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(114, 'Bursitis', 'Inflammation of a bursa (small, fluid-filled sac that cushions bones, tendons, and muscles near joints).', 'M71.9', 'low', 'common', 'Adults', 'all', 'Orthopedist/Primary Care/PT', 1, 'Days to weeks, can recur', NULL, 'Overview of bursitis, commonly affecting shoulder, elbow, hip, knee.', 'Achy or stiff joint, pain that worsens with movement or pressure, swelling, redness.', 'Signs of septic bursitis (fever, severe pain, warmth, spreading redness) - requires urgent care.', 'Repetitive motion, prolonged pressure, trauma, infection, underlying conditions like arthritis.', 'Rest, ice, NSAIDs, aspiration of fluid, corticosteroid injections, antibiotics (if septic).', 'Joint pain, swelling, tenderness.', 'Irritation/inflammation of bursa.', 'Chronic pain, limited mobility.', 'Physical exam, X-ray (to rule out bone issues), ultrasound, aspiration for lab analysis.', 'Clinical diagnosis, imaging if needed.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(115, 'Scoliosis', 'Sideways curvature of the spine.', 'M41.9', 'medium', 'chronic', 'Often develops in adolescence', 'female', 'Orthopedist/Spine Specialist', 0, 'Can progress if untreated', NULL, 'Overview of different types of scoliosis and their management.', 'Uneven shoulders, one shoulder blade more prominent, uneven waist, one hip higher, leaning to one side. Often painless initially.', 'Rapid progression of curve, severe back pain, breathing difficulties (in severe cases).', 'Idiopathic (most common), congenital, neuromuscular conditions.', 'Observation, bracing (for growing children with moderate curves), surgery (spinal fusion for severe curves), physical therapy.', 'Spinal curvature, asymmetry.', 'Unknown (idiopathic), congenital, neuromuscular.', 'Back pain, respiratory issues, cosmetic concerns.', 'Physical exam (Adams forward bend test), X-rays (scoliogram).', 'X-ray measurement of Cobb angle.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(116, 'Osteoporosis', 'Condition where bones become weak and brittle, increasing risk of fractures.', 'M81.0', 'medium', 'chronic', 'Older adults, esp. postmenopausal women', 'female', 'Endocrinologist/Rheumatologist/Orthopedist', 0, 'Lifelong management', NULL, 'Overview of osteoporosis, risk factors, and prevention.', 'Often asymptomatic until a fracture occurs. May include back pain (from vertebral fractures), loss of height, stooped posture.', 'Sudden severe back pain (possible vertebral fracture), hip fracture after minor fall.', 'Age, female gender, menopause, family history, low calcium/vitamin D intake, smoking, alcohol abuse, sedentary lifestyle, certain medications.', 'Calcium/vitamin D supplements, weight-bearing exercise, medications (bisphosphonates, denosumab, etc.).', 'Usually silent until fracture.', 'Bone resorption outpaces formation.', 'Fractures (hip, spine, wrist).', 'Bone density scan (DXA scan).', 'DXA scan T-score.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(117, 'Rotator Cuff Tear', 'Tear in one or more of the four rotator cuff tendons in the shoulder.', 'M75.1', 'medium', 'acute', 'Adults, esp. older or athletes', 'all', 'Orthopedist/Sports Medicine/PT', 0, 'Variable, may require surgery', NULL, 'Overview of rotator cuff injuries.', 'Dull ache deep in the shoulder, pain when lifting/lowering arm or with specific movements, weakness in arm, difficulty sleeping on affected side.', 'Sudden severe shoulder pain and inability to lift arm after an injury.', 'Injury (fall, direct blow), repetitive overhead activity, degeneration with age.', 'Rest, ice, NSAIDs, physical therapy, corticosteroid injections, surgery (arthroscopic repair).', 'Shoulder pain, weakness.', 'Trauma or degeneration.', 'Chronic pain, loss of function, adhesive capsulitis.', 'Physical exam (specific tests), MRI, ultrasound.', 'Clinical exam, confirmed by MRI/ultrasound.', NULL, NULL, NULL, NULL, 19, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18');
INSERT INTO `conditions` (`condition_id`, `condition_name`, `description`, `icd_code`, `urgency_level`, `condition_type`, `age_relevance`, `gender_relevance`, `specialist_type`, `self_treatable`, `typical_duration`, `educational_content`, `overview`, `regular_symptoms_text`, `emergency_symptoms_text`, `risk_factors_text`, `treatment_protocols_text`, `symptoms_text`, `causes_text`, `complications_text`, `testing_details`, `diagnosis_details`, `condition_image_filename`, `condition_video_filename`, `testing_type_id`, `diagnosis_type_id`, `department_id`, `is_active`, `created_at`, `updated_at`) VALUES
(119, 'Acne Vulgaris', 'Clogged hair follicles causing pimples, blackheads, whiteheads.', 'L70.0', 'low', 'common', 'Adolescents, young adults', 'all', 'Dermatologist', 1, 'Variable, can be chronic', NULL, 'Overview of Acne.', 'Pimples, oily skin.', 'Severe cystic acne, widespread rash with fever.', 'Hormones, genetics, diet.', 'Topicals, oral meds.', 'Pimples, blackheads.', 'Oil, bacteria, inflammation.', 'Scarring, hyperpigmentation.', 'Clinical diagnosis.', 'Visual inspection.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(120, 'Eczema (Atopic Dermatitis)', 'Chronic condition causing red, itchy, inflamed skin.', 'L20.9', 'medium', 'chronic', 'Children, can persist', 'all', 'Dermatologist', 0, 'Chronic, flare-ups', NULL, 'Overview of Eczema.', 'Dry, itchy, red patches.', 'Widespread severe rash, skin infection signs.', 'Family history, immune issues.', 'Moisturizers, topicals, biologics.', 'Itchy, red, dry skin.', 'Genetics, environment.', 'Skin infections, sleep issues.', 'Clinical diagnosis, allergy tests.', 'Appearance, history.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(121, 'Psoriasis', 'Autoimmune condition causing rapid skin cell buildup, forming scales.', 'L40.9', 'medium', 'chronic', 'Adults, any age', 'all', 'Dermatologist', 0, 'Chronic, flare-ups', NULL, 'Overview of Psoriasis.', 'Red patches with silvery scales, itching.', 'Erythrodermic psoriasis (widespread redness).', 'Family history, immune issues, stress.', 'Topicals, phototherapy, systemics.', 'Red, scaly plaques, itching.', 'Autoimmune disorder.', 'Psoriatic arthritis, CVD.', 'Clinical diagnosis, biopsy.', 'Appearance, biopsy if needed.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(122, 'Rosacea', 'Chronic skin condition causing redness, visible blood vessels, and sometimes small, red, pus-filled bumps on the face.', 'L71.9', 'low', 'chronic', 'Adults (30-60), fair-skinned', 'female', 'Dermatologist', 0, 'Chronic, with flare-ups', NULL, 'Overview of rosacea subtypes and triggers.', 'Facial redness/flushing, visible blood vessels (telangiectasias), pimple-like bumps (papules/pustules), eye irritation (ocular rosacea), thickened skin (rhinophyma in severe cases).', 'Severe ocular symptoms, uncontrolled inflammation.', 'Genetics, environmental triggers (sun, heat, spicy foods, alcohol), Demodex mites (possible role).', 'Topical medications (metronidazole, azelaic acid, ivermectin), oral antibiotics, laser therapy, trigger avoidance.', 'Facial redness, bumps, flushing.', 'Unknown, multifactorial.', 'Eye complications, rhinophyma.', 'Clinical diagnosis based on appearance and history.', 'Visual inspection of facial skin.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(123, 'Basal Cell Carcinoma (BCC)', 'Most common type of skin cancer, slow-growing, rarely spreads.', 'C44 (varies by site)', 'medium', 'common', 'Older adults, sun-exposed individuals', 'all', 'Dermatologist', 0, 'Curable with treatment', NULL, 'Overview of BCC, the most common skin cancer.', 'Pearly or waxy bump, flat flesh-colored or brown scar-like lesion, sore that heals and reopens.', 'Rapid growth, bleeding, ulceration, or signs of local invasion.', 'Chronic sun exposure, fair skin, history of sunburns, weakened immune system.', 'Surgical excision, Mohs surgery, cryotherapy, topical treatments, radiation.', 'Persistent non-healing sore or bump.', 'UV radiation damage to DNA.', 'Local recurrence, disfigurement if untreated.', 'Skin biopsy.', 'Histopathological examination of biopsy.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(124, 'Squamous Cell Carcinoma (SCC)', 'Second most common skin cancer, can spread if untreated.', 'C44 (varies by site)', 'medium', 'common', 'Older adults, sun-exposed individuals', 'all', 'Dermatologist', 0, 'Curable with early treatment', NULL, 'Overview of SCC and its potential for metastasis.', 'Firm, red nodule; flat lesion with a scaly, crusted surface; sore that heals and then reopens.', 'Rapid growth, large size, deep invasion, tenderness, bleeding, metastasis (rare but possible).', 'Chronic sun exposure, fair skin, history of sunburns, actinic keratoses, weakened immune system, HPV infection (some types).', 'Surgical excision, Mohs surgery, radiation, cryotherapy, chemotherapy (for advanced cases).', 'Scaly patch, firm nodule, sore.', 'UV radiation damage, chronic inflammation.', 'Metastasis, recurrence.', 'Skin biopsy.', 'Histopathological examination of biopsy.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(125, 'Melanoma', 'Most serious type of skin cancer, can spread rapidly.', 'C43.9', 'high', 'common', 'All ages, increased risk with sun exposure', 'all', 'Dermatologist/Oncologist', 0, 'Curable if caught early, dangerous if advanced', NULL, 'Overview of melanoma and the ABCDEs of detection.', 'Asymmetrical mole, irregular Border, uneven Color, Diameter >6mm, Evolving (changing) mole. New mole or existing mole that changes.', 'Any suspicious mole fitting ABCDE criteria, bleeding mole, rapidly growing lesion. Potential for metastasis makes early detection critical.', 'UV radiation (sun exposure, tanning beds), fair skin, many moles, family history of melanoma, history of blistering sunburns.', 'Surgical excision, sentinel lymph node biopsy, immunotherapy, targeted therapy, chemotherapy, radiation (for advanced disease).', 'Changing or new suspicious mole.', 'UV damage to melanocytes.', 'Metastasis to lymph nodes and distant organs.', 'Skin exam, dermoscopy, skin biopsy (excisional).', 'Histopathological examination, Breslow depth, Clark level.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(126, 'Tinea Pedis (Athlete\'s Foot)', 'Fungal infection affecting the skin on the feet.', 'B35.3', 'low', 'common', 'All ages, esp. those with sweaty feet/public showers', 'all', 'Dermatologist/Primary Care', 1, 'Days to weeks with treatment', NULL, 'Overview of athlete\'s foot and prevention.', 'Itchy, scaly rash, often between toes; cracking, peeling skin; blisters; burning or stinging sensation.', 'Signs of secondary bacterial infection (pus, spreading redness, fever).', 'Warm, moist environments; occlusive footwear; public showers/pools; compromised skin barrier.', 'Topical antifungal creams/powders, oral antifungals (for severe or resistant cases), keeping feet dry.', 'Itchy, scaly feet.', 'Dermatophyte fungi.', 'Secondary bacterial infection, spread to nails (onychomycosis).', 'Clinical appearance, KOH prep (skin scraping microscopy), fungal culture.', 'Usually clinical, KOH prep for confirmation.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(127, 'Verruca Vulgaris (Common Warts)', 'Small, rough growths caused by human papillomavirus (HPV).', 'B07.9', 'low', 'common', 'Children and young adults primarily', 'all', 'Dermatologist/Primary Care', 1, 'Months to years, can resolve spontaneously', NULL, 'Overview of common warts and treatment options.', 'Rough, grainy skin growths, often on hands/fingers; may have tiny black dots (clotted blood vessels).', 'Rapidly spreading warts, warts that are painful or bleed easily, warts in sensitive areas (genitals, face).', 'Direct contact with HPV, broken skin, weakened immune system.', 'Salicylic acid, cryotherapy (freezing), cantharidin, laser treatment, immunotherapy, surgical removal.', 'Rough skin growths.', 'Human Papillomavirus (HPV).', 'Spread to other body parts or people, cosmetic concerns.', 'Clinical appearance.', 'Visual inspection.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18'),
(128, 'Contact Dermatitis', 'Skin inflammation caused by direct contact with an irritant or allergen.', 'L23-L25 (varies by t', 'low', 'common', 'All ages', 'all', 'Dermatologist/Allergist', 1, 'Days to weeks after removal of trigger', NULL, 'Overview of irritant and allergic contact dermatitis.', 'Red rash, itching, blisters (sometimes), dry/cracked/scaly skin, burning/stinging sensation. Rash typically limited to area of contact.', 'Severe widespread rash, signs of infection, involvement of face/genitals causing significant discomfort.', 'Irritants (soaps, detergents, chemicals), allergens (poison ivy, nickel, fragrances, preservatives).', 'Avoidance of trigger, topical corticosteroids, oral antihistamines, cool compresses, moisturizers. Patch testing for allergic contact dermatitis.', 'Itchy rash after contact.', 'Irritant or allergen exposure.', 'Secondary infection, chronic dermatitis if trigger not identified.', 'Clinical history and appearance, patch testing (for allergic type).', 'Clinical diagnosis, patch testing.', NULL, NULL, NULL, NULL, 20, 1, '2025-05-30 12:13:18', '2025-05-30 12:13:18');

-- --------------------------------------------------------

--
-- Table structure for table `departments`
--

CREATE TABLE `departments` (
  `department_id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `image_filename` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `departments`
--

INSERT INTO `departments` (`department_id`, `name`, `description`, `image_filename`, `created_at`, `updated_at`) VALUES
(17, 'Cardiology', 'Heart disease remains the leading cause of death worldwide. Early detection and treatment with modern cardiology techniques can significantly reduce risks and improve patient outcomes. Our center offers comprehensive diagnostics and cutting-edge therapies for all cardiovascular conditions.', 'uploads/department_images/heart_0f4975c972a74954a3b75fbacfd0c9fc.jpeg', '2025-05-09 16:33:47', '2025-05-09 20:24:35'),
(18, 'Neurology', 'Neurological disorders affect millions worldwide. Early detection and advanced treatment techniques can significantly improve patient outcomes. Our center offers comprehensive diagnostics and cutting-edge therapies for all neurological conditions.', 'uploads/department_images/Neuron_eb6033e77c8e40adace4d4c368d2ae4a.jpeg', '2025-05-09 20:36:07', NULL),
(19, 'Orthopedics', 'Musculoskeletal conditions affect millions of people worldwide. Early diagnosis and treatment with modern orthopedic techniques can significantly improve mobility, reduce pain, and enhance quality of life. Our center offers comprehensive diagnostics and cutting-edge therapies for all orthopedic conditions.', 'uploads/department_images/ortho_45705d6130f4452491a4ad7da1d3db7e.jpg', '2025-05-09 20:37:43', NULL),
(20, 'Dermatology', 'Dermatology is the branch of medicine dealing with the skin. It is a speciality with both medical and surgical aspects.', 'uploads/department_images/derma_78cdd00c165848e7bdc77fd241623b76.jpeg', '2025-05-09 20:41:55', '2025-05-09 23:42:09'),
(21, 'Nutrition Services', 'None', NULL, '2025-05-12 16:05:04', '2025-05-27 01:18:33');

-- --------------------------------------------------------

--
-- Table structure for table `diagnoses`
--

CREATE TABLE `diagnoses` (
  `diagnosis_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `doctor_id` int(11) DEFAULT NULL,
  `diagnosis_date` date NOT NULL,
  `diagnosis_code` varchar(20) DEFAULT NULL,
  `diagnosis_name` varchar(100) NOT NULL,
  `diagnosis_type` enum('preliminary','differential','final','working') DEFAULT 'final',
  `description` text DEFAULT NULL,
  `treatment_details` text DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `treatment_plan` text DEFAULT NULL,
  `follow_up_required` tinyint(1) DEFAULT 0,
  `follow_up_date` date DEFAULT NULL,
  `follow_up_type` varchar(50) DEFAULT NULL,
  `severity` enum('mild','moderate','severe','critical','unknown') DEFAULT 'unknown',
  `prognosis` text DEFAULT NULL,
  `is_chronic` tinyint(1) DEFAULT 0,
  `is_resolved` tinyint(1) DEFAULT 0,
  `resolved_date` date DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_by` int(11) NOT NULL,
  `updated_by` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `diagnoses`
--

INSERT INTO `diagnoses` (`diagnosis_id`, `patient_id`, `doctor_id`, `diagnosis_date`, `diagnosis_code`, `diagnosis_name`, `diagnosis_type`, `description`, `treatment_details`, `notes`, `treatment_plan`, `follow_up_required`, `follow_up_date`, `follow_up_type`, `severity`, `prognosis`, `is_chronic`, `is_resolved`, `resolved_date`, `created_at`, `updated_at`, `created_by`, `updated_by`) VALUES
(1, 46, 43, '2025-05-13', 'I10', 'Hypertension (High Blood Pressure)', 'final', 'Hypertension is often called the \"silent killer\" because it usually has no warning signs or symptoms. Many people do not know they have it.', NULL, NULL, NULL, 0, NULL, NULL, 'critical', NULL, 1, 0, NULL, '2025-05-13 19:22:54', '2025-05-13 19:22:54', 43, 43),
(2, 46, 43, '2025-05-24', 'L20', 'Atopic Dermatitis (Eczema)', 'final', 'Atopic dermatitis is long lasting (chronic) and tends to flare periodically. It may be accompanied by asthma or hay fever.', NULL, NULL, NULL, 0, NULL, NULL, 'unknown', NULL, 0, 0, NULL, '2025-05-24 19:53:52', '2025-05-24 19:53:52', 43, 43),
(3, 48, 43, '2025-05-30', 'I42.9', 'Cardiomyopathy', 'final', 'Overview of different types of cardiomyopathy.', NULL, NULL, NULL, 0, NULL, NULL, 'unknown', NULL, 0, 0, NULL, '2025-05-30 16:22:00', '2025-05-30 16:22:00', 43, 43),
(4, 48, 43, '2025-05-30', 'S00-T88 (varies by l', 'Bone Fracture', 'final', 'Overview of different types of bone fractures.', NULL, 'ads', 'ads', 1, '2025-05-31', '3- month check', 'moderate', NULL, 1, 1, '2025-05-30', '2025-05-30 17:02:53', '2025-05-30 17:02:53', 43, 43),
(5, 48, 43, '2025-05-30', 'M54.5', 'Low Back Pain', 'final', 'Overview of Low Back Pain.', NULL, 'ads', 'ads', 1, '2025-06-02', '3- month check', 'severe', NULL, 0, 0, NULL, '2025-05-30 17:03:38', '2025-05-30 17:03:38', 43, 43);

-- --------------------------------------------------------

--
-- Table structure for table `diagnosis_types`
--

CREATE TABLE `diagnosis_types` (
  `diagnosis_type_id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `diagnosis_types`
--

INSERT INTO `diagnosis_types` (`diagnosis_type_id`, `name`, `description`, `created_at`) VALUES
(6, 'Clinical Diagnosis', 'Diagnosis made based on signs, symptoms, and medical history, without laboratory confirmation.', '2025-05-29 19:59:39'),
(7, 'Laboratory Diagnosis', 'Diagnosis confirmed by laboratory tests (e.g., blood tests, cultures).', '2025-05-29 19:59:39'),
(8, 'Radiological Diagnosis', 'Diagnosis made or confirmed using imaging techniques (e.g., X-ray, CT scan, MRI).', '2025-05-29 19:59:39'),
(9, 'Pathological Diagnosis', 'Diagnosis based on the microscopic examination of tissues or cells (e.g., biopsy).', '2025-05-29 19:59:39'),
(10, 'Differential Diagnosis', 'A list of possible diagnoses ranked in order of probability, used to guide further investigation.', '2025-05-29 19:59:39'),
(11, 'Working Diagnosis', 'A preliminary diagnosis made by a physician based on initial findings, subject to change as more information becomes available.', '2025-05-29 19:59:39'),
(12, 'Final Diagnosis', 'The definitive diagnosis established after all necessary investigations and evaluations.', '2025-05-29 19:59:39'),
(13, 'Presumptive Diagnosis', 'A diagnosis made with a high degree of certainty based on typical symptoms and signs, before full confirmation.', '2025-05-29 19:59:39'),
(14, 'Syndromic Diagnosis', 'Diagnosis based on a recognized pattern of symptoms and signs that constitute a particular syndrome.', '2025-05-29 19:59:39');

-- --------------------------------------------------------

--
-- Table structure for table `diet_plans`
--

CREATE TABLE `diet_plans` (
  `plan_id` int(11) NOT NULL,
  `plan_name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `plan_type` enum('standard','custom','medical','weight_loss','weight_gain','maintenance') NOT NULL,
  `calories` int(11) DEFAULT NULL,
  `protein_grams` int(11) DEFAULT NULL,
  `carbs_grams` int(11) DEFAULT NULL,
  `fat_grams` int(11) DEFAULT NULL,
  `fiber_grams` int(11) DEFAULT NULL,
  `sodium_mg` int(11) DEFAULT NULL,
  `is_public` tinyint(1) DEFAULT 0,
  `creator_id` int(11) DEFAULT NULL,
  `target_conditions` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `updated_by` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `diet_plans`
--

INSERT INTO `diet_plans` (`plan_id`, `plan_name`, `description`, `plan_type`, `calories`, `protein_grams`, `carbs_grams`, `fat_grams`, `fiber_grams`, `sodium_mg`, `is_public`, `creator_id`, `target_conditions`, `created_at`, `updated_at`, `updated_by`) VALUES
(4, 'DIET PLAN TEST 1', 'None', 'standard', 994, 48, 152, 24, NULL, NULL, 1, 43, NULL, '2025-05-12 17:36:47', '2025-05-27 22:40:18', 43);

-- --------------------------------------------------------

--
-- Table structure for table `diet_plan_food_items`
--

CREATE TABLE `diet_plan_food_items` (
  `item_id` int(11) NOT NULL,
  `meal_id` int(11) NOT NULL,
  `food_name` varchar(100) NOT NULL,
  `serving_size` varchar(50) NOT NULL,
  `calories` int(11) DEFAULT NULL,
  `protein_grams` decimal(6,2) DEFAULT NULL,
  `carbs_grams` decimal(6,2) DEFAULT NULL,
  `fat_grams` decimal(6,2) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `alternatives` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `diet_plan_food_items`
--

INSERT INTO `diet_plan_food_items` (`item_id`, `meal_id`, `food_name`, `serving_size`, `calories`, `protein_grams`, `carbs_grams`, `fat_grams`, `notes`, `alternatives`, `created_at`, `updated_at`) VALUES
(41, 13, 'Almond Milk, unsweetened', '1 cup (240ml)', 30, 1.00, 1.00, 2.50, 'None', 'None', '2025-05-13 00:09:21', '2025-05-13 00:18:44'),
(42, 13, 'Apple, Fuji, medium', '1 medium (approx 180g)', 95, 0.50, 25.10, 0.30, 'None', 'None', '2025-05-13 00:09:21', '2025-05-13 00:18:44'),
(43, 13, 'Oats, rolled, dry', '1/2 cup (40g)', 150, 5.00, 27.00, 3.00, 'None', 'None', '2025-05-13 00:09:21', '2025-05-13 00:18:44'),
(44, 14, 'Almonds, raw', '1 oz (approx 23 kernels, 28g)', 164, 6.00, 6.10, 14.20, 'None', 'None', '2025-05-13 00:18:44', '2025-05-13 00:19:57'),
(45, 14, 'Watermelon, diced', '1 cup (152g)', 46, 0.90, 11.50, 0.20, 'None', 'None', '2025-05-13 00:18:44', '2025-05-13 00:19:57'),
(46, 15, 'Rice, white, long-grain, cooked', '1 cup (158g)', 205, 4.30, 44.50, 0.40, 'None', 'None', '2025-05-13 00:19:57', '2025-05-13 00:20:55'),
(47, 15, 'Potato, Russet, baked, flesh and skin', '1 medium (173g)', 164, 4.60, 37.20, 0.20, 'None', 'None', '2025-05-13 00:19:57', '2025-05-13 00:20:55'),
(48, 15, 'Chicken Breast, boneless, skinless, grilled', '3 oz (85g)', 140, 26.00, NULL, 3.50, 'None', 'None', '2025-05-13 00:19:57', '2025-05-13 00:20:55');

-- --------------------------------------------------------

--
-- Table structure for table `diet_plan_meals`
--

CREATE TABLE `diet_plan_meals` (
  `meal_id` int(11) NOT NULL,
  `plan_id` int(11) NOT NULL,
  `meal_name` varchar(100) NOT NULL,
  `meal_type` enum('breakfast','lunch','dinner','snack','other') NOT NULL,
  `protein_grams` int(11) DEFAULT NULL,
  `time_of_day` time DEFAULT NULL,
  `description` text DEFAULT NULL,
  `calories` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `carbs_grams` int(11) DEFAULT NULL,
  `fat_grams` int(11) DEFAULT NULL,
  `fiber_grams` int(11) DEFAULT NULL,
  `sodium_mg` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `diet_plan_meals`
--

INSERT INTO `diet_plan_meals` (`meal_id`, `plan_id`, `meal_name`, `meal_type`, `protein_grams`, `time_of_day`, `description`, `calories`, `created_at`, `updated_at`, `carbs_grams`, `fat_grams`, `fiber_grams`, `sodium_mg`) VALUES
(13, 4, 'TEST MEAL 1', 'breakfast', 7, '09:00:00', 'TEST 1', 275, '2025-05-12 17:38:09', '2025-05-13 00:58:37', 53, 6, NULL, NULL),
(14, 4, 'TEST MEAL 2', 'snack', 7, '11:00:00', 'None', 210, '2025-05-13 00:18:44', '2025-05-13 00:58:37', 18, 14, NULL, NULL),
(15, 4, 'TEST MEAL 3', 'lunch', 35, '15:20:00', 'None', 509, '2025-05-13 00:19:57', '2025-05-13 00:58:37', 82, 4, NULL, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `doctors`
--

CREATE TABLE `doctors` (
  `user_id` int(11) NOT NULL,
  `specialization_id` int(11) NOT NULL,
  `license_number` varchar(50) DEFAULT NULL,
  `license_state` varchar(50) DEFAULT NULL,
  `license_expiration` date DEFAULT NULL,
  `npi_number` varchar(20) DEFAULT NULL,
  `medical_school` varchar(100) DEFAULT NULL,
  `graduation_year` int(11) DEFAULT NULL,
  `certifications` text DEFAULT NULL,
  `accepting_new_patients` tinyint(1) DEFAULT 1,
  `biography` text DEFAULT NULL,
  `profile_photo_url` varchar(255) DEFAULT NULL,
  `clinic_address` text DEFAULT NULL,
  `verification_status` enum('pending','approved','rejected','pending_info') DEFAULT 'pending',
  `approval_date` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL,
  `department_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `doctors`
--

INSERT INTO `doctors` (`user_id`, `specialization_id`, `license_number`, `license_state`, `license_expiration`, `npi_number`, `medical_school`, `graduation_year`, `certifications`, `accepting_new_patients`, `biography`, `profile_photo_url`, `clinic_address`, `verification_status`, `approval_date`, `updated_at`, `department_id`) VALUES
(43, 20, 'DOC-84234', 'None', '2026-02-22', '1324123412', 'None', NULL, 'iquwhfoiwhueroichpewhvp', 1, 'qwuyfgwuyergfyewghoirchp9wehrpbvwer', 'uploads/profile_pics/d2212d65bb454ddb9ec139b1b3716e8d.png', 'None', 'approved', '2025-05-09 23:00:04', '2025-05-27 20:22:52', 21),
(51, 15, 'DOC-83293', 'GAZ', '2026-05-20', '1345627890', 'Hines-Mullins Medical Schooleiurhfoyuewbroucvbew', 2012, 'iquwhfoiwhueroichpewhvwe.rnvk.w rv.p', 1, 'asldfnvern;vnjw;rejtnv;jwnr;otv', NULL, NULL, 'approved', NULL, '2025-05-27 01:32:23', 17),
(54, 15, 'DOC-842222', 'GIZA', '2027-04-02', '1231231121', 'None', 2010, 'None', 1, 'None', 'uploads/profile_pics/80c4ce3219ba4c6bb49eba4429443b91.png', 'None', 'approved', '2025-05-26 23:48:36', '2025-05-30 16:04:09', 17);

-- --------------------------------------------------------

--
-- Table structure for table `doctor_availability_overrides`
--

CREATE TABLE `doctor_availability_overrides` (
  `override_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL COMMENT 'FK to users.user_id (doctor)',
  `doctor_location_id` int(11) DEFAULT NULL COMMENT 'FK to doctor_locations. If NULL, applies generally. If set, applies ONLY to this location.',
  `override_date` date NOT NULL,
  `start_time` time DEFAULT NULL COMMENT 'If NULL, applies to the whole day at the specified location (or generally)',
  `end_time` time DEFAULT NULL COMMENT 'If NULL, applies to the whole day at the specified location (or generally)',
  `is_unavailable` tinyint(1) NOT NULL DEFAULT 1 COMMENT 'True=block time, False=make extra time available',
  `reason` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `doctor_documents`
--

CREATE TABLE `doctor_documents` (
  `document_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL,
  `document_type` enum('license','certification','identity','education','other') NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_path` varchar(255) NOT NULL,
  `file_size` int(11) NOT NULL,
  `upload_date` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `doctor_locations`
--

CREATE TABLE `doctor_locations` (
  `doctor_location_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL COMMENT 'FK to users.user_id where user_type = doctor',
  `location_name` varchar(255) NOT NULL COMMENT 'A name for the doctor to identify this location (e.g., Main Clinic, Hospital Office)',
  `address` text NOT NULL COMMENT 'Full street address',
  `city` varchar(100) DEFAULT NULL,
  `state` varchar(50) DEFAULT NULL,
  `zip_code` varchar(20) DEFAULT NULL,
  `country` varchar(50) DEFAULT 'United States',
  `phone_number` varchar(20) DEFAULT NULL COMMENT 'Specific phone for this location',
  `is_primary` tinyint(1) DEFAULT 0 COMMENT 'Indicates the doctor''s main practice location',
  `is_active` tinyint(1) DEFAULT 1 COMMENT 'Allows disabling without deleting',
  `notes` text DEFAULT NULL COMMENT 'Doctor''s private notes about this location',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `google_maps_link` varchar(1024) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `doctor_locations`
--

INSERT INTO `doctor_locations` (`doctor_location_id`, `doctor_id`, `location_name`, `address`, `city`, `state`, `zip_code`, `country`, `phone_number`, `is_primary`, `is_active`, `notes`, `created_at`, `updated_at`, `google_maps_link`) VALUES
(2, 43, 'Main Clinicewrvwervwr', '35 syria streetawfewrfer', 'wervrvrwmohandsin', 'Gizaweverwvw', '126552232', 'Egyptfsavfdv', '0100792319520', 1, 1, 'Noneadcasvcsercvewvr', '2025-05-12 09:27:15', '2025-05-27 16:04:35', 'https://maps.app.goo.gl/xAkoEBFoBvkfvaDp9'),
(4, 43, 'Clinic 1', '46 Shehab street', 'mohandsin', 'الجيزة', '12655', 'Egypt', '01007919520', 0, 1, NULL, '2025-05-24 17:43:15', '2025-05-24 17:44:20', 'https://maps.app.goo.gl/UPbGJTmLdq11L7zV9'),
(5, 43, 'Clinic 2', '300 Gameet Dowal street', 'mohandsin', 'الجيزة', '12655', 'Egypt', '01007919520', 0, 1, NULL, '2025-05-24 19:08:48', '2025-05-24 19:08:48', 'https://maps.app.goo.gl/xAkoEBFoBvkfvaDp9'),
(7, 51, 'Main Clinic TEST', '35 syria street', 'mohandsin', 'الجيزة', '12655', 'Egypt', '01007919520', 0, 1, NULL, '2025-05-26 22:38:56', '2025-05-26 22:38:56', NULL),
(8, 43, 'Main Clinic TEST', '35 syria street', 'mohandsin', 'الجيزة', '12655', 'Egypt', '01007919520', 0, 1, 'dsafewfcvawervre', '2025-05-27 16:03:51', '2025-05-27 16:04:35', 'https://maps.app.goo.gl/xAkoEBFoBvkfvaDp9');

-- --------------------------------------------------------

--
-- Table structure for table `doctor_location_availability`
--

CREATE TABLE `doctor_location_availability` (
  `location_availability_id` int(11) NOT NULL,
  `doctor_location_id` int(11) NOT NULL COMMENT 'FK to doctor_locations link',
  `day_of_week` tinyint(4) NOT NULL COMMENT '0 = Sunday, 6 = Saturday',
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `doctor_location_availability`
--

INSERT INTO `doctor_location_availability` (`location_availability_id`, `doctor_location_id`, `day_of_week`, `start_time`, `end_time`, `created_at`, `updated_at`) VALUES
(5, 2, 0, '15:00:00', '18:00:00', '2025-05-14 20:13:05', '2025-05-14 20:13:05'),
(6, 2, 0, '18:30:00', '20:30:00', '2025-05-14 20:13:50', '2025-05-14 20:13:50'),
(7, 4, 0, '10:00:00', '14:00:00', '2025-05-24 19:09:23', '2025-05-24 19:09:23');

-- --------------------------------------------------------

--
-- Table structure for table `doctor_location_daily_caps`
--

CREATE TABLE `doctor_location_daily_caps` (
  `cap_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL COMMENT 'FK to users.user_id (doctor)',
  `doctor_location_id` int(11) NOT NULL COMMENT 'FK to doctor_locations.doctor_location_id',
  `day_of_week` tinyint(4) NOT NULL COMMENT '0=Sunday, 1=Monday, ..., 6=Saturday',
  `max_appointments` int(10) UNSIGNED NOT NULL COMMENT 'Max appointments allowed for this doctor, at this location, on this day of the week',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Stores recurring daily appointment caps for doctors per location and day of week.';

--
-- Dumping data for table `doctor_location_daily_caps`
--

INSERT INTO `doctor_location_daily_caps` (`cap_id`, `doctor_id`, `doctor_location_id`, `day_of_week`, `max_appointments`, `created_at`, `updated_at`) VALUES
(1, 43, 2, 0, 20, '2025-05-14 20:14:12', '2025-05-14 20:14:13');

-- --------------------------------------------------------

--
-- Table structure for table `doctor_reviews`
--

CREATE TABLE `doctor_reviews` (
  `review_id` int(11) NOT NULL,
  `doctor_id` int(11) NOT NULL,
  `reviewer_id` int(11) NOT NULL,
  `review_date` datetime NOT NULL DEFAULT current_timestamp(),
  `action` enum('viewed','approved','rejected','info_requested') NOT NULL,
  `notes` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `food_item_library`
--

CREATE TABLE `food_item_library` (
  `food_item_id` int(11) NOT NULL,
  `item_name` varchar(255) NOT NULL,
  `serving_size` varchar(100) NOT NULL,
  `calories` int(11) DEFAULT NULL,
  `protein_grams` decimal(10,2) DEFAULT NULL,
  `carbs_grams` decimal(10,2) DEFAULT NULL,
  `fat_grams` decimal(10,2) DEFAULT NULL,
  `fiber_grams` decimal(10,2) DEFAULT NULL,
  `sodium_mg` int(11) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT 1,
  `creator_id` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `food_item_library`
--

INSERT INTO `food_item_library` (`food_item_id`, `item_name`, `serving_size`, `calories`, `protein_grams`, `carbs_grams`, `fat_grams`, `fiber_grams`, `sodium_mg`, `notes`, `is_active`, `creator_id`, `created_at`, `updated_at`) VALUES
(1, 'Apple', '1', 200, 13.00, 27.00, 12.00, 30.00, 1, NULL, 0, 43, '2025-05-12 23:44:43', '2025-05-12 23:53:15'),
(2, 'Apple, Fuji, medium', '1 medium (approx 180g)', 95, 0.50, 25.10, 0.30, 4.40, 2, 'Good source of fiber.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(3, 'Banana, medium', '1 medium (approx 118g)', 105, 1.30, 27.00, 0.40, 3.10, 1, 'Good source of potassium.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(4, 'Orange, Navel, medium', '1 medium (approx 140g)', 69, 1.30, 17.60, 0.20, 3.10, 0, 'Excellent source of Vitamin C.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(5, 'Strawberries, raw', '1 cup, halves (166g)', 53, 1.10, 12.70, 0.50, 3.30, 2, 'Rich in antioxidants.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(6, 'Blueberries, raw', '1 cup (148g)', 84, 1.10, 21.40, 0.50, 3.60, 1, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(7, 'Grapes, Red or Green, seedless', '1 cup (approx 151g)', 104, 1.10, 27.30, 0.20, 1.40, 3, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(8, 'Avocado, California, half', '1/2 medium (approx 68g)', 114, 1.30, 5.90, 10.50, 4.60, 5, 'Good source of healthy fats.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(9, 'Watermelon, diced', '1 cup (152g)', 46, 0.90, 11.50, 0.20, 0.60, 2, 'High water content.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(10, 'Pineapple, chunks', '1 cup (165g)', 83, 0.90, 21.70, 0.20, 2.30, 2, 'Contains bromelain.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(11, 'Mango, sliced', '1 cup (165g)', 99, 1.40, 24.70, 0.60, 2.60, 2, 'Good source of Vitamin A.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(12, 'Broccoli, raw', '1 cup, chopped (91g)', 31, 2.50, 6.00, 0.30, 2.40, 30, 'Good source of Vitamin C and K.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(13, 'Carrot, raw', '1 medium (61g)', 25, 0.60, 5.80, 0.10, 1.70, 42, 'Good source of Vitamin A.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(14, 'Spinach, raw', '1 cup (30g)', 7, 0.90, 1.10, 0.10, 0.70, 24, 'Rich in iron and Vitamin K.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(15, 'Bell Pepper, Red, raw', '1 medium (approx 119g)', 30, 1.20, 6.00, 0.30, 2.50, 4, 'Excellent source of Vitamin C.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(16, 'Cucumber, with peel, sliced', '1 cup (104g)', 16, 0.70, 3.80, 0.10, 0.50, 2, 'High water content.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(17, 'Tomato, red, ripe, raw', '1 medium (123g)', 22, 1.10, 4.80, 0.20, 1.50, 6, 'Good source of lycopene.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(18, 'Lettuce, Romaine, shredded', '1 cup (47g)', 8, 0.60, 1.60, 0.10, 1.00, 4, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(19, 'Onion, yellow, chopped', '1 cup (160g)', 64, 1.80, 14.90, 0.20, 2.70, 6, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(20, 'Potato, Russet, baked, flesh and skin', '1 medium (173g)', 164, 4.60, 37.20, 0.20, 4.00, 10, 'Good source of potassium.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(21, 'Sweet Potato, baked in skin', '1 medium (114g)', 103, 2.30, 23.60, 0.20, 3.80, 41, 'Excellent source of Vitamin A.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(22, 'Zucchini, cooked, boiled, drained, sliced', '1 cup (180g)', 27, 2.10, 5.10, 0.60, 2.00, 5, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(23, 'Mushrooms, white, raw, sliced', '1 cup (70g)', 15, 2.20, 2.30, 0.20, 0.70, 2, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(24, 'Rice, white, long-grain, cooked', '1 cup (158g)', 205, 4.30, 44.50, 0.40, 0.60, 2, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(25, 'Rice, brown, long-grain, cooked', '1 cup (195g)', 216, 5.00, 44.80, 1.80, 3.50, 10, 'Whole grain.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(26, 'Oats, rolled, dry', '1/2 cup (40g)', 150, 5.00, 27.00, 3.00, 4.00, 0, 'Good source of soluble fiber.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(27, 'Bread, whole wheat', '1 slice (approx 32g)', 81, 3.90, 13.80, 1.10, 1.90, 146, 'Contains gluten.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(28, 'Bread, white', '1 slice (approx 25g)', 66, 2.10, 12.60, 0.80, 0.60, 147, 'Contains gluten.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(29, 'Pasta, whole wheat, cooked', '1 cup (140g)', 174, 7.50, 37.20, 0.80, 6.30, 4, 'Contains gluten.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(30, 'Pasta, enriched, cooked', '1 cup spaghetti (140g)', 221, 8.10, 43.20, 1.30, 2.50, 1, 'Contains gluten.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(31, 'Quinoa, cooked', '1 cup (185g)', 222, 8.10, 39.40, 3.60, 5.20, 13, 'Complete protein source.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(32, 'Chicken Breast, boneless, skinless, grilled', '3 oz (85g)', 140, 26.00, 0.00, 3.50, 0.00, 65, 'Lean protein source.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(33, 'Salmon, Atlantic, baked', '3 oz (85g)', 175, 21.60, 0.00, 9.30, 0.00, 50, 'Rich in Omega-3 fatty acids.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(34, 'Egg, large, hard-boiled', '1 large (50g)', 78, 6.30, 0.60, 5.30, 0.00, 62, NULL, 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(35, 'Tofu, firm', '1/2 cup (126g)', 94, 10.10, 2.30, 5.00, 1.90, 9, 'Plant-based protein.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(36, 'Lentils, brown, cooked', '1 cup (198g)', 230, 17.90, 39.90, 0.80, 15.60, 4, 'High in fiber and protein.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(37, 'Beef, Ground, 90% lean, pan-browned', '3 oz (85g)', 184, 21.30, 0.00, 10.50, 0.00, 70, 'Good source of iron.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(38, 'Shrimp, cooked, moist heat', '3 oz (85g)', 84, 20.40, 0.20, 0.20, 0.00, 94, 'Low in fat.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(39, 'Chickpeas (garbanzo beans), canned, drained', '1 cup (164g)', 269, 14.50, 45.00, 4.20, 12.50, 11, 'Rinse well to reduce sodium.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(40, 'Black Beans, canned, drained, rinsed', '1 cup (172g)', 218, 14.50, 40.80, 0.70, 16.60, 2, 'Good source of fiber.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(41, 'Milk, Whole (3.25% fat)', '1 cup (244g)', 149, 7.70, 11.70, 8.00, 0.00, 105, 'Contains lactose.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(42, 'Milk, Skim (nonfat)', '1 cup (245g)', 83, 8.30, 12.20, 0.20, 0.00, 103, 'Contains lactose.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(43, 'Yogurt, Plain, Greek, Nonfat', '1 container (6 oz or 170g)', 100, 17.30, 6.10, 0.40, 0.00, 61, 'High protein. Contains lactose.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(44, 'Cheese, Cheddar', '1 oz (28g)', 115, 6.70, 1.00, 9.60, 0.00, 185, 'Contains lactose.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(45, 'Almond Milk, unsweetened', '1 cup (240ml)', 30, 1.00, 1.00, 2.50, 1.00, 180, 'Dairy-free alternative.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(46, 'Soy Milk, original, unsweetened', '1 cup (240ml)', 80, 7.00, 4.00, 4.00, 2.00, 90, 'Dairy-free alternative.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(47, 'Olive Oil, extra virgin', '1 tablespoon (14g)', 120, 0.00, 0.00, 14.00, 0.00, 0, 'Source of monounsaturated fats.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(48, 'Almonds, raw', '1 oz (approx 23 kernels, 28g)', 164, 6.00, 6.10, 14.20, 3.50, 0, 'Good source of Vitamin E.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(49, 'Walnuts, halves', '1 oz (approx 14 halves, 28g)', 185, 4.30, 3.90, 18.50, 1.90, 1, 'Source of Omega-3 (ALA).', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(50, 'Peanut Butter, smooth style, with salt', '2 tablespoons (32g)', 191, 7.10, 7.70, 16.10, 1.60, 137, 'Contains peanuts.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42'),
(51, 'Chia Seeds, dried', '1 tablespoon (12g)', 60, 2.00, 5.00, 4.00, 4.00, 2, 'High in fiber and Omega-3.', 1, NULL, '2025-05-12 23:52:42', '2025-05-12 23:52:42');

-- --------------------------------------------------------

--
-- Table structure for table `insurance_providers`
--

CREATE TABLE `insurance_providers` (
  `id` int(11) NOT NULL,
  `provider_name` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `message_attachments`
--

CREATE TABLE `message_attachments` (
  `attachment_id` int(11) NOT NULL,
  `message_id` int(11) NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_type` varchar(100) NOT NULL,
  `file_size` int(11) NOT NULL,
  `file_path` varchar(255) NOT NULL,
  `uploaded_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `patients`
--

CREATE TABLE `patients` (
  `user_id` int(11) NOT NULL,
  `date_of_birth` date NOT NULL,
  `gender` enum('male','female','other','prefer_not_to_say','unknown') NOT NULL DEFAULT 'unknown',
  `blood_type` enum('A+','A-','B+','B-','AB+','AB-','O+','O-','Unknown') DEFAULT 'Unknown',
  `height_cm` decimal(5,2) DEFAULT NULL,
  `weight_kg` decimal(5,2) DEFAULT NULL,
  `insurance_provider_id` int(11) DEFAULT NULL,
  `insurance_policy_number` varchar(50) DEFAULT NULL,
  `insurance_group_number` varchar(50) DEFAULT NULL,
  `insurance_expiration` date DEFAULT NULL,
  `marital_status` enum('single','married','divorced','widowed','separated','other') DEFAULT NULL,
  `occupation` varchar(100) DEFAULT NULL,
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `patients`
--

INSERT INTO `patients` (`user_id`, `date_of_birth`, `gender`, `blood_type`, `height_cm`, `weight_kg`, `insurance_provider_id`, `insurance_policy_number`, `insurance_group_number`, `insurance_expiration`, `marital_status`, `occupation`, `updated_at`) VALUES
(46, '2002-06-21', 'male', 'B-', 190.00, 135.00, NULL, 'None', 'None', NULL, 'single', 'Student', '2025-05-27 00:43:50'),
(47, '1999-02-02', 'female', 'Unknown', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-27 00:43:50'),
(48, '2003-06-27', 'female', 'O-', 165.00, 65.00, NULL, NULL, NULL, NULL, 'single', NULL, '2025-05-27 00:43:50'),
(56, '2002-06-28', 'female', 'B-', 165.00, 65.00, NULL, NULL, NULL, NULL, 'single', 'Student', '2025-05-27 00:48:06');

-- --------------------------------------------------------

--
-- Table structure for table `patient_allergies`
--

CREATE TABLE `patient_allergies` (
  `patient_id` int(11) NOT NULL,
  `allergy_id` int(11) NOT NULL,
  `severity` enum('mild','moderate','severe','unknown') DEFAULT 'unknown',
  `reaction_description` text DEFAULT NULL,
  `diagnosed_date` date DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `patient_medical_reports`
--

CREATE TABLE `patient_medical_reports` (
  `report_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `document_name` varchar(255) NOT NULL,
  `document_type` varchar(100) NOT NULL,
  `report_format` varchar(10) DEFAULT 'json',
  `file_path` varchar(512) NOT NULL,
  `submission_date` datetime NOT NULL DEFAULT current_timestamp(),
  `notes` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `patient_symptoms`
--

CREATE TABLE `patient_symptoms` (
  `patient_symptom_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `symptom_id` int(11) NOT NULL,
  `reported_date` date NOT NULL,
  `onset_date` date DEFAULT NULL,
  `severity` varchar(50) DEFAULT NULL,
  `duration` varchar(50) DEFAULT NULL,
  `frequency` enum('constant','intermittent','occasional','rare') DEFAULT NULL,
  `triggers` text DEFAULT NULL,
  `alleviating_factors` text DEFAULT NULL,
  `worsening_factors` text DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `reported_by` int(11) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `patient_vaccinations`
--

CREATE TABLE `patient_vaccinations` (
  `patient_vaccination_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `vaccine_id` int(11) NOT NULL COMMENT 'FK to your vaccines table',
  `administration_date` date NOT NULL,
  `dose_number` varchar(20) DEFAULT NULL COMMENT 'e.g., 1, 2, Booster',
  `lot_number` varchar(50) DEFAULT NULL,
  `administered_by_id` int(11) DEFAULT NULL COMMENT 'FK to users table (doctor/nurse)',
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `patient_vaccinations`
--

INSERT INTO `patient_vaccinations` (`patient_vaccination_id`, `patient_id`, `vaccine_id`, `administration_date`, `dose_number`, `lot_number`, `administered_by_id`, `notes`, `created_at`, `updated_at`) VALUES
(1, 48, 40, '2025-05-30', '1', NULL, 43, NULL, '2025-05-30 17:05:04', '2025-05-30 17:05:04');

-- --------------------------------------------------------

--
-- Table structure for table `pending_registrations`
--

CREATE TABLE `pending_registrations` (
  `id` int(11) NOT NULL,
  `email` varchar(100) NOT NULL,
  `first_name` varchar(50) NOT NULL,
  `last_name` varchar(50) NOT NULL,
  `username` varchar(50) NOT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `country` varchar(50) DEFAULT NULL,
  `user_type_requested` enum('doctor') NOT NULL,
  `specialization_id` int(11) DEFAULT NULL,
  `license_number` varchar(50) DEFAULT NULL,
  `license_state` varchar(50) DEFAULT NULL,
  `license_expiration` date DEFAULT NULL,
  `date_submitted` datetime NOT NULL DEFAULT current_timestamp(),
  `status` enum('pending','approved_user_created','rejected') NOT NULL DEFAULT 'pending',
  `user_id` int(11) DEFAULT NULL,
  `processed_by` int(11) DEFAULT NULL,
  `date_processed` datetime DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `department_id` int(11) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `pending_registrations`
--

INSERT INTO `pending_registrations` (`id`, `email`, `first_name`, `last_name`, `username`, `phone`, `country`, `user_type_requested`, `specialization_id`, `license_number`, `license_state`, `license_expiration`, `date_submitted`, `status`, `user_id`, `processed_by`, `date_processed`, `notes`, `department_id`, `password`) VALUES
(2, 'adham@doctor.com', 'Adham', 'Elgohary', 'Adham@Doctor', '+201007919520', 'Egypt', 'doctor', 16, 'DOC-84297', 'Giza', '2026-02-20', '2025-05-09 22:43:14', 'approved_user_created', 43, 42, '2025-05-09 23:00:04', 'Doctor approved and account activated.', 17, 'scrypt:32768:8:1$C1eXo7QevLUO9I5i$550ccd77c19729481c91cb25be2a4a86330845d89477e097de6cd1cce7cb0bc0839a7720e05c9ae05d0965e4ca02ea16bf0543f55a2f06a56e76f07ab77d3361'),
(3, 'nourhan@doctor.com', 'Nourhan', 'Tarek', 'Nourhan@doctor', NULL, 'Egypt', 'doctor', 15, 'DOC-842222', 'GIZA', '2027-04-02', '2025-05-26 23:36:54', 'approved_user_created', 54, 42, '2025-05-26 23:48:36', 'Doctor approved and account activated.', 17, 'scrypt:32768:8:1$LYUirt2PISbwSD3g$ab0a66d970a0009a9df4cbb5702d285793cef60a57aba2739d8d7393512062cf4bfbdb72a58ebac388f980d0bbb210f473999718e2fd5911183dc40de83d0f79');

-- --------------------------------------------------------

--
-- Table structure for table `specializations`
--

CREATE TABLE `specializations` (
  `specialization_id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `department_id` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `specializations`
--

INSERT INTO `specializations` (`specialization_id`, `name`, `description`, `department_id`, `created_at`, `updated_at`) VALUES
(13, 'General Cardiology', 'Focuses on the diagnosis, treatment, and prevention of a wide range of cardiovascular diseases, including coronary artery disease, heart failure, arrhythmias, and valvular heart disease. Manages overall heart health and coordinates care.', 17, '2025-05-09 17:25:32', '2025-05-09 17:25:32'),
(14, 'Interventional Cardiology', 'Specializes in catheter-based treatments for heart conditions, such as angioplasty, stent placement for coronary artery disease, transcatheter valve repair/replacement (e.g., TAVR, MitraClip), and closure of congenital heart defects.', 17, '2025-05-09 17:25:50', '2025-05-09 17:25:50'),
(15, 'Cardiac Electrophysiology', 'Deals with the diagnosis and treatment of heart rhythm disorders (arrhythmias). Performs procedures like electrophysiology studies, catheter ablations, and implantation of pacemakers and implantable cardioverter-defibrillators (ICDs).', 17, '2025-05-09 17:26:04', '2025-05-09 17:26:04'),
(16, 'Advanced Heart Failure and Transplant Cardiology', 'Manages patients with advanced stages of heart failure, including evaluation for and management of heart transplantation and mechanical circulatory support devices (e.g., LVADs).', 17, '2025-05-09 17:26:21', '2025-05-09 17:26:21'),
(17, 'Non-Invasive Cardiology (Cardiac Imaging)', 'Focuses on diagnosing heart conditions using non-invasive imaging techniques such as echocardiography (ultrasound of the heart), cardiac CT, cardiac MRI, and nuclear cardiology (stress tests).', 17, '2025-05-09 17:26:35', '2025-05-09 17:26:35'),
(18, 'Preventive Cardiology', 'Emphasizes the prevention of heart disease through risk factor assessment and modification, including management of hypertension, hyperlipidemia (high cholesterol), diabetes, and lifestyle counseling (diet, exercise, smoking cessation).', 17, '2025-05-09 17:26:49', '2025-05-09 17:26:49'),
(19, 'Unknown', NULL, NULL, '2025-05-09 20:00:04', '2025-05-09 20:00:04'),
(20, 'Registered Dietitian', NULL, 21, '2025-05-12 16:13:48', '2025-05-12 16:13:48');

-- --------------------------------------------------------

--
-- Table structure for table `symptoms`
--

CREATE TABLE `symptoms` (
  `symptom_id` int(11) NOT NULL,
  `symptom_name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `body_area` varchar(50) DEFAULT NULL,
  `icd_code` varchar(20) DEFAULT NULL,
  `common_causes` text DEFAULT NULL,
  `severity_scale` varchar(255) DEFAULT NULL,
  `symptom_category` enum('common','rare','emergency','chronic') DEFAULT NULL,
  `age_relevance` varchar(100) DEFAULT NULL,
  `gender_relevance` enum('all','male','female') DEFAULT 'all',
  `question_text` text DEFAULT NULL,
  `follow_up_questions` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- --------------------------------------------------------

--
-- Table structure for table `testing_types`
--

CREATE TABLE `testing_types` (
  `testing_type_id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `testing_types`
--

INSERT INTO `testing_types` (`testing_type_id`, `name`, `description`, `created_at`) VALUES
(8, 'Blood Test', 'Analysis of a blood sample to detect diseases, measure levels of substances, or check organ function.', '2025-05-29 19:59:31'),
(9, 'Urine Test (Urinalysis)', 'Analysis of urine to detect and manage a wide range of disorders, such as urinary tract infections, kidney disease, and diabetes.', '2025-05-29 19:59:31'),
(10, 'Imaging Scan', 'Techniques like X-ray, CT, MRI, Ultrasound to create pictures of the inside of the body.', '2025-05-29 19:59:31'),
(11, 'Biopsy', 'Removal of a small sample of tissue for examination under a microscope to diagnose diseases like cancer.', '2025-05-29 19:59:31'),
(12, 'Endoscopy', 'Procedure using a thin, lighted tube with a camera to look inside a body cavity or organ.', '2025-05-29 19:59:31'),
(13, 'Genetic Testing', 'Analysis of DNA to identify changes in genes that may cause illness or disease.', '2025-05-29 19:59:31'),
(14, 'Culture Test', 'Growing microorganisms (like bacteria or fungi) from a sample to identify an infection.', '2025-05-29 19:59:31'),
(15, 'Physical Examination', 'Systematic assessment of a patient\'s body to detect signs of disease.', '2025-05-29 19:59:31'),
(16, 'Swab Test', 'Collecting a sample from a surface (e.g., throat, nose, wound) using a sterile swab for analysis.', '2025-05-29 19:59:31'),
(17, 'Stool Test', 'Analysis of a stool sample to diagnose certain conditions affecting the digestive tract.', '2025-05-29 19:59:31'),
(18, 'Pulmonary Function Test (PFT)', 'Noninvasive tests that show how well the lungs are working.', '2025-05-29 19:59:31'),
(19, 'Electrocardiogram (ECG/EKG)', 'Records the electrical signal from the heart to check for different heart conditions.', '2025-05-29 19:59:31'),
(20, 'Electroencephalogram (EEG)', 'Records brain wave patterns to diagnose conditions like epilepsy or sleep disorders.', '2025-05-29 19:59:31'),
(21, 'Allergy Skin Test', 'Skin tests used to identify allergens causing allergic reactions.', '2025-05-29 19:59:31'),
(22, 'Biomarker Test', 'Tests that look for genes, proteins, and other substances (called biomarkers or tumor markers) that can provide information about cancer or other conditions.', '2025-05-29 19:59:31');

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `user_id` int(11) NOT NULL,
  `username` varchar(50) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `first_name` varchar(50) NOT NULL,
  `last_name` varchar(50) NOT NULL,
  `user_type` enum('patient','doctor','admin') NOT NULL,
  `phone` varchar(30) DEFAULT NULL,
  `country` varchar(50) DEFAULT 'United States',
  `profile_picture` varchar(255) DEFAULT NULL,
  `account_status` enum('active','inactive','suspended','pending') DEFAULT 'active',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`user_id`, `username`, `email`, `password`, `first_name`, `last_name`, `user_type`, `phone`, `country`, `profile_picture`, `account_status`, `created_at`, `updated_at`) VALUES
(42, 'Adham@admin', 'Adham@Adminstrator.com', 'scrypt:32768:8:1$x4g4K7UDbg8ezIan$9edb091089835d4ed623d43a20865ed37477adc6add0044109c98e40ac79fd2dc84b66447a98ee73d30c5e58a1cc5f70e1aed1437069d2b9262dce755a2936fa', 'Adham', 'Elgohary', 'admin', NULL, 'United States', NULL, 'active', '2025-05-09 16:39:37', '2025-05-26 16:15:27'),
(43, 'Adham@Doctor', 'adham@doctor.com', 'scrypt:32768:8:1$6NlMRQ6DkjVNa9zn$c9fc7f6eacd9421ac85430af11b451ec167873b63654a3eca4ac1ad3cb70204e23fecbf27fe3b89e1b7c22b7ee076bf6c8dd0efe2759710fb3d00392c657fc55', 'Adham', 'Elgohary', 'doctor', '+201007919520', 'Egypt', NULL, 'active', '2025-05-09 20:00:04', '2025-05-27 17:22:52'),
(46, 'Adham@patient', 'Adham@patient.com', 'scrypt:32768:8:1$DOZEBNkdlE3zUWOb$5a6036cd18f034358e43c50d71a3a65380cfb5ffd84cccdecff7ba760e13230e7a5bccae1b1cb08c0ef68f7d853634d78e45d7c5f934de6d5e2a8ea0862ddd34', 'adham', 'elgohary', 'patient', '01007919520', 'Egypt', 'uploads/profile_pics/user_46_profile_1748612308.png', 'active', '2025-05-09 20:25:25', '2025-05-30 13:38:28'),
(47, 'nohaHamza', 'nnnn@nn.com', 'scrypt:32768:8:1$fgL2MEJErZn0Wxtj$dd36629294ba93d3466d0631fed3989118d52c31fc388680638fef66063793baa32ea10b04f8e2f69a75dd25413ae5a63b46cb9fd683c0a0002fad7aff06cee9', 'noha', 'hamza', 'patient', NULL, 'United States', NULL, 'active', '2025-05-12 09:43:28', '2025-05-12 09:43:28'),
(48, 'Reem@2368', 'reem@patient.com', 'scrypt:32768:8:1$SHputMswauKMbQHs$26105a0dca04264368f513f6a66ad673644c07fb48a35f532ba8f6f9eabe5d0feb4480d17179bb45f739af23bef94b8c2ab0c0d376bfbb9e6dea8125172fd2f4', 'Reem', 'Hosni', 'patient', '0101010101010', 'Egypt', NULL, 'active', '2025-05-25 21:17:45', '2025-05-25 21:18:49'),
(50, 'Reem@admin', 'Reem@adminstartor.com', 'scrypt:32768:8:1$0HBh0VTfWR2tTerY$c9be962701d73ac21bddee341b4e96ba994dffaf89c0634df1a6cf5ed58e83d81126bea3b03713184c9ca83e0a4fced1b9f2d5e1d143b7910696af59fb525572', 'Reem', 'Hosni', 'admin', NULL, 'United States', NULL, 'active', '2025-05-26 18:23:21', '2025-05-26 18:23:32'),
(51, 'Reem@doctor', 'reem@doctor.com', 'scrypt:32768:8:1$QayUA4gL7K4oDz7Z$64868e0a9f2725125789e9b24f0bebb09e20a16f5c94fabd07f0bf04befd30128362f473eeaf19470e68b863acfbb7d15663f09cc94d178f22f784de80087faf', 'Reem', 'Hosni', 'doctor', '215346512', 'United States', NULL, 'active', '2025-05-26 18:29:30', '2025-05-26 22:30:35'),
(54, 'Nourhan@doctor', 'nourhan@doctor.com', 'scrypt:32768:8:1$LYUirt2PISbwSD3g$ab0a66d970a0009a9df4cbb5702d285793cef60a57aba2739d8d7393512062cf4bfbdb72a58ebac388f980d0bbb210f473999718e2fd5911183dc40de83d0f79', 'Nourhan', 'Tarek', 'doctor', 'None', 'Egypt', NULL, 'active', '2025-05-26 20:48:36', '2025-05-27 19:14:57'),
(56, 'Nourhan@patient', 'Nourhan@patient.com', 'scrypt:32768:8:1$PewxrGHE1aCYq4aO$5582378e549b314c11a9ed52bbdd4d40588a7fbc4e0a6d80d7e75206f961d19493010f9a77957b0ef8443616de8ac1799e96d892629d974a4f2cc9903371ff36', 'Nourhan', 'Tarek', 'patient', '01007919520', 'United States', NULL, 'active', '2025-05-26 21:01:30', '2025-05-27 19:20:32');

--
-- Triggers `users`
--
DELIMITER $$
CREATE TRIGGER `after_users_insert_professional` AFTER INSERT ON `users` FOR EACH ROW BEGIN
    DECLARE unknown_spec_id INT;
    DECLARE default_spec_id INT;

    IF NEW.user_type = 'doctor' THEN
        IF NOT EXISTS (SELECT 1 FROM doctors WHERE user_id = NEW.user_id) THEN
            SELECT specialization_id INTO unknown_spec_id
            FROM specializations WHERE name = 'Unknown' LIMIT 1;

            IF unknown_spec_id IS NULL THEN
               INSERT IGNORE INTO specializations (name, department_id) VALUES ('Unknown', NULL);
               SET unknown_spec_id = LAST_INSERT_ID();
            END IF;
            SET default_spec_id = unknown_spec_id;

            INSERT INTO doctors (
                user_id, specialization_id, license_number, license_state,
                license_expiration, verification_status, accepting_new_patients, updated_at
            ) VALUES (
                NEW.user_id, default_spec_id, 'PENDING_VERIFICATION', 'XX',
                CURDATE() + INTERVAL 1 YEAR, 'pending', TRUE, NOW()
            );
        END IF;
    ELSEIF NEW.user_type = 'patient' THEN
        IF NOT EXISTS (SELECT 1 FROM patients WHERE user_id = NEW.user_id) THEN
            INSERT INTO patients (user_id, date_of_birth, gender)
            VALUES (NEW.user_id, '1900-01-01', 'unknown');
        END IF;
    ELSEIF NEW.user_type = 'admin' THEN
         IF NOT EXISTS (SELECT 1 FROM admins WHERE user_id = NEW.user_id) THEN
            INSERT INTO admins (user_id, admin_level)
            VALUES (NEW.user_id, 'regular');
         END IF;
    END IF;

    -- Optional Role Assignment Logic (Example)
    -- DECLARE patient_role_id INT; DECLARE doctor_role_id INT; DECLARE admin_role_id INT;
    -- SELECT role_id INTO patient_role_id FROM roles WHERE role_name = 'Patient' LIMIT 1;
    -- SELECT role_id INTO doctor_role_id FROM roles WHERE role_name = 'Doctor' LIMIT 1;
    -- SELECT role_id INTO admin_role_id FROM roles WHERE role_name = 'Admin' LIMIT 1;
    -- IF NEW.user_type = 'patient' AND patient_role_id IS NOT NULL THEN INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (NEW.user_id, patient_role_id);
    -- ELSEIF NEW.user_type = 'doctor' AND doctor_role_id IS NOT NULL THEN INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (NEW.user_id, doctor_role_id);
    -- ELSEIF NEW.user_type = 'admin' AND admin_role_id IS NOT NULL THEN INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (NEW.user_id, admin_role_id);
    -- END IF;

END
$$
DELIMITER ;

-- --------------------------------------------------------

--
-- Table structure for table `user_diet_plans`
--

CREATE TABLE `user_diet_plans` (
  `user_diet_plan_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `plan_id` int(11) NOT NULL,
  `assigned_by` int(11) DEFAULT NULL,
  `start_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `active` tinyint(1) DEFAULT 1,
  `compliance_rating` int(11) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `vaccines`
--

CREATE TABLE `vaccines` (
  `vaccine_id` int(11) NOT NULL,
  `category_id` int(11) NOT NULL,
  `vaccine_name` varchar(255) NOT NULL,
  `abbreviation` varchar(50) DEFAULT NULL,
  `diseases_prevented` text NOT NULL,
  `recommended_for` text DEFAULT NULL,
  `benefits` text DEFAULT NULL,
  `timing_schedule` text DEFAULT NULL,
  `number_of_doses` varchar(50) DEFAULT NULL,
  `booster_information` text DEFAULT NULL,
  `vaccine_type` varchar(100) DEFAULT NULL,
  `administration_route` varchar(100) DEFAULT NULL,
  `common_side_effects` text DEFAULT NULL,
  `contraindications_precautions` text DEFAULT NULL,
  `storage_requirements` text DEFAULT NULL,
  `manufacturer` varchar(255) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `is_active` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `vaccines`
--

INSERT INTO `vaccines` (`vaccine_id`, `category_id`, `vaccine_name`, `abbreviation`, `diseases_prevented`, `recommended_for`, `benefits`, `timing_schedule`, `number_of_doses`, `booster_information`, `vaccine_type`, `administration_route`, `common_side_effects`, `contraindications_precautions`, `storage_requirements`, `manufacturer`, `notes`, `created_at`, `updated_at`, `is_active`) VALUES
(18, 5, 'Hepatitis B (HepB)', 'HepB', 'Hepatitis B virus infection', 'All infants, beginning at birth, and unvaccinated children and adolescents. Also recommended for adults at risk for HBV infection.', 'Prevents Hepatitis B infection, which can lead to chronic liver disease, cirrhosis, liver cancer, and death. Protects against a common cause of liver cancer worldwide.', 'Birth, 1-2 months, 6-18 months (3 doses)', '3 doses', NULL, 'Recombinant Subunit', NULL, 'Soreness at the injection site, mild fever.', 'Severe allergic reaction (e.g., anaphylaxis) after a previous dose or to a vaccine component.', NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(19, 5, 'Rotavirus (RV)', 'RV', 'Rotavirus gastroenteritis', NULL, NULL, '2, 4 months (2 doses - Rotarix) OR 2, 4, 6 months (3 doses - RotaTeq)', '2-3 doses', NULL, 'Live Attenuated (Oral)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(20, 5, 'Diphtheria, Tetanus, & Acellular Pertussis (DTaP)', 'DTaP', 'Diphtheria, Tetanus, Pertussis (Whooping Cough)', NULL, NULL, '2, 4, 6, 15-18 months, 4-6 years (5 doses)', '5 doses', NULL, 'Toxoid & Acellular Components', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(21, 5, 'Haemophilus influenzae type b (Hib)', 'Hib', 'Invasive Hib disease (e.g., meningitis, epiglottitis)', NULL, NULL, '2, 4, 6 (brand dependent), 12-15 months (3 or 4 doses)', '3-4 doses', NULL, 'Polysaccharide Conjugate', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(22, 5, 'Pneumococcal Conjugate (PCV13/PCV15)', 'PCV', 'Invasive pneumococcal disease (e.g., meningitis, bacteremia, pneumonia)', NULL, NULL, '2, 4, 6, 12-15 months (4 doses)', '4 doses', NULL, 'Polysaccharide Conjugate', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(23, 5, 'Inactivated Poliovirus (IPV)', 'IPV', 'Poliomyelitis', NULL, NULL, '2, 4, 6-18 months, 4-6 years (4 doses)', '4 doses', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(24, 5, 'Measles, Mumps, Rubella (MMR)', 'MMR', 'Measles, Mumps, Rubella', NULL, NULL, '12-15 months, 4-6 years (2 doses)', '2 doses', NULL, 'Live Attenuated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(25, 5, 'Varicella (Chickenpox)', 'VAR', 'Varicella (Chickenpox)', NULL, NULL, '12-15 months, 4-6 years (2 doses)', '2 doses', NULL, 'Live Attenuated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(26, 5, 'Hepatitis A (HepA - Child)', 'HepA-Child', 'Hepatitis A virus infection', NULL, NULL, '12-23 months (2 doses, 6 months apart)', '2 doses', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(27, 6, 'Tetanus, Diphtheria, & Acellular Pertussis (Tdap)', 'Tdap', 'Tetanus, Diphtheria, Pertussis', NULL, NULL, 'Age 11-12 (1 dose), then Td or Tdap booster every 10 years. Also for pregnant women each pregnancy.', '1 dose (adolescent), then boosters', NULL, 'Toxoid & Acellular Components', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(28, 6, 'Human Papillomavirus (HPV)', 'HPV', 'HPV-related cancers and genital warts', NULL, NULL, 'Recommended for ages 11-12 (can start at 9); 2 or 3 doses depending on age at first dose. Catch-up through age 26.', '2-3 doses', NULL, 'Recombinant L1 Protein', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(29, 6, 'Meningococcal Conjugate (MenACWY)', 'MenACWY', 'Meningococcal disease (serogroups A, C, W, Y)', NULL, NULL, 'Age 11-12 (1 dose), booster at age 16. Others at increased risk.', '1-2 doses', NULL, 'Polysaccharide Conjugate', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(30, 6, 'Meningococcal B (MenB)', 'MenB', 'Meningococcal disease (serogroup B)', NULL, NULL, 'Ages 16-23 (shared clinical decision-making, 2 or 3 doses depending on brand)', '2-3 doses', NULL, 'Recombinant Protein', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(31, 6, 'Pneumococcal Polysaccharide (PPSV23)', 'PPSV23', 'Invasive pneumococcal disease', NULL, NULL, 'Adults 65+ (1 dose). Younger adults with certain medical conditions.', '1-2 doses', NULL, 'Polysaccharide', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(32, 6, 'Recombinant Zoster Vaccine (Shingles)', 'RZV', 'Shingles (Herpes Zoster) and postherpetic neuralgia', NULL, NULL, 'Adults 50+ (2 doses, 2-6 months apart)', '2 doses', NULL, 'Recombinant Subunit, Adjuvanted', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(33, 7, 'Typhoid Fever', 'Typhoid', 'Typhoid fever', NULL, NULL, 'At least 1-2 weeks before travel, depending on vaccine type (oral or injectable). Booster needed.', NULL, NULL, 'Live Attenuated (Oral) or Polysaccharide (Injectable)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(34, 7, 'Yellow Fever', 'YF', 'Yellow fever', NULL, NULL, 'At least 10 days before travel to endemic areas. Certificate may be required.', NULL, NULL, 'Live Attenuated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(35, 7, 'Japanese Encephalitis', 'JE', 'Japanese encephalitis', NULL, NULL, 'For travelers to specific regions in Asia, series of 2 doses.', '2 doses', NULL, 'Inactivated Virus or Live Attenuated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(36, 7, 'Rabies (Pre-exposure)', 'Rabies-PrEP', 'Rabies', NULL, NULL, 'For travelers with high risk of animal bites (e.g., vets, long-term travelers in high-risk areas). 2-dose series.', '2 doses', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(37, 7, 'Cholera', 'Cholera', 'Cholera', NULL, NULL, 'For travelers to areas with active cholera transmission. Single oral dose.', '1 dose (oral)', NULL, 'Live Attenuated (Oral)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(38, 7, 'Hepatitis A (Travel)', 'HepA-Travel', 'Hepatitis A virus infection', NULL, NULL, 'If not previously vaccinated. 2 doses, 6-18 months apart. First dose before travel.', '2 doses', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(39, 8, 'Influenza (Flu Vaccine)', 'Flu', 'Seasonal Influenza', 'All individuals 6 months of age and older each influenza season.', 'Reduces the risk of flu illness, hospitalization, and death. Can also reduce severity of illness if one does get the flu. Helps protect vulnerable individuals in the community.', 'Annually for everyone 6 months and older.', '1 dose (some children may need 2 doses)', NULL, 'Inactivated, Recombinant, or Live Attenuated (Nasal)', NULL, 'Soreness, redness, or swelling where shot was given, low-grade headache, fever, muscle aches, nausea, fatigue. Nasal spray vaccine might cause runny nose, wheezing, headache, vomiting, muscle aches, fever.', 'Severe, life-threatening allergies to flu vaccine or any ingredient in the vaccine. People who have had Guillain-Barré Syndrome (GBS) should discuss vaccination with their doctor. Some people with egg allergies may need specific considerations.', NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(40, 8, 'COVID-19 Vaccine', 'COVID-19', 'COVID-19 (SARS-CoV-2 infection)', NULL, NULL, 'Primary series and boosters as recommended by public health authorities. Varies by age and vaccine type.', NULL, NULL, 'mRNA, Viral Vector, Protein Subunit (varies by manufacturer)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(41, 8, 'Tdap (Pregnancy)', 'Tdap-Preg', 'Tetanus, Diphtheria, Pertussis (to protect newborn)', NULL, NULL, 'One dose during each pregnancy, preferably between 27 and 36 weeks gestation.', '1 dose per pregnancy', NULL, 'Toxoid & Acellular Components', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:39:38', '2025-05-29 20:39:38', 1),
(42, 5, 'Influenza (Childhood)', 'Flu-Child', 'Seasonal Influenza', NULL, 'Reduces risk of flu, hospitalization, and flu-related complications in children.', 'Annually for children 6 months and older. Children 6mo-8yr may need 2 doses the first year they are vaccinated.', '1-2 doses annually', NULL, 'Inactivated, Recombinant, or Live Attenuated (Nasal)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(52, 6, 'Pneumococcal (Adult - PCV15/PCV20 or PPSV23)', 'Pneumo-Adult', 'Invasive pneumococcal disease, pneumococcal pneumonia', NULL, 'Prevents severe infections caused by pneumococcal bacteria.', 'Adults 65+ (PCV20 alone, or PCV15 followed by PPSV23). Younger adults (19-64) with certain chronic medical conditions or risk factors.', '1 or 2 doses', NULL, 'Polysaccharide Conjugate (PCV) / Polysaccharide (PPSV23)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(53, 6, 'Hepatitis A (Adult)', 'HepA-Adult', 'Hepatitis A virus infection', NULL, 'Prevents Hepatitis A liver infection.', 'Adults at risk (e.g., travelers, MSM, drug users, chronic liver disease, occupational risk) if not previously vaccinated. 2 doses, 6-18 months apart.', '2 doses', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(59, 7, 'Cholera (Oral)', 'Cholera-Oral', 'Cholera (bacterial disease causing severe diarrhea)', NULL, 'Reduces risk of cholera in high-risk areas.', 'For travelers to areas with active cholera transmission. Single oral dose at least 10 days before travel.', '1 dose (oral)', NULL, 'Live Attenuated (Oral)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(60, 7, 'Polio (Booster for Travel)', 'IPV-Travel', 'Poliomyelitis', NULL, 'Maintains immunity against polio when traveling to at-risk regions.', 'Adults who completed primary series and are traveling to areas with poliovirus circulation may need a one-time lifetime booster.', '1 booster dose', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(65, 8, 'Influenza (Annual Flu Vaccine)', 'Flu-Annual', 'Seasonal Influenza', 'All individuals 6 months of age and older each influenza season.', 'Reduces the risk of flu illness, hospitalization, and death. Can also reduce severity of illness if one does get the flu. Helps protect vulnerable individuals in the community.', 'Annually for everyone 6 months and older.', '1 dose annually (some children may need 2 doses in', NULL, 'Inactivated, Recombinant, or Live Attenuated (Nasal)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(66, 8, 'COVID-19 Vaccine (Current Formulation)', 'COVID-19-Current', 'COVID-19 (SARS-CoV-2 infection)', NULL, 'Reduces risk of severe illness, hospitalization, and death from COVID-19. Helps reduce spread.', 'Primary series and updated (e.g., annual) boosters as recommended by public health authorities. Varies by age, vaccine type, and current circulating variants.', 'Varies', NULL, 'mRNA, Viral Vector, Protein Subunit (varies)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(67, 8, 'Tdap (for Pregnant Women)', 'Tdap-Pregnancy', 'Tetanus, Diphtheria, Pertussis (for maternal and infant protection)', NULL, 'Protects the mother and provides passive immunity to the newborn against pertussis.', 'One dose of Tdap during each pregnancy, preferably between 27 and 36 weeks gestation, to pass antibodies to the newborn.', '1 dose per pregnancy', NULL, 'Toxoid & Acellular Components', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(68, 8, 'Respiratory Syncytial Virus (RSV) Vaccine (Older Adults)', 'RSV-OA', 'Respiratory Syncytial Virus lower respiratory tract disease', NULL, 'Reduces risk of severe RSV illness in older adults.', 'Adults 60 years and older (shared clinical decision-making). Single dose.', '1 dose', NULL, 'Recombinant Protein, Adjuvanted', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(69, 8, 'Respiratory Syncytial Virus (RSV) Monoclonal Antibody (Infants/Pregnancy)', 'RSV-MAB', 'RSV lower respiratory tract disease in infants', NULL, 'Prevents severe RSV disease in infants.', 'For infants born during or entering their first RSV season (passive immunization via monoclonal antibody) OR maternal RSV vaccination during pregnancy (32-36 weeks gestation) to protect infant.', '1 dose (infant MAB or maternal vaccine)', NULL, 'Monoclonal Antibody (Nirsevimab) or Recombinant Protein (Maternal)', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(70, 8, 'Dengue Vaccine', 'Dengvaxia/Qdenga', 'Dengue fever', 'Specific populations in endemic areas with prior infection. Qdenga may have broader indication.', 'Reduces risk of severe dengue in previously infected individuals.', 'For individuals aged 6-45 years (depending on vaccine) with laboratory-confirmed previous dengue infection, living in dengue-endemic areas. 2 or 3 dose series.', '2-3 doses', NULL, 'Live Attenuated Chimeric Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1),
(71, 8, 'Tick-Borne Encephalitis (TBE) Vaccine', 'TBE', 'Tick-Borne Encephalitis', NULL, 'Prevents TBE, a serious viral infection of the central nervous system.', 'For individuals in or traveling to TBE-endemic areas (parts of Europe and Asia) with outdoor exposure. 3-dose primary series, with boosters.', '3 doses + boosters', NULL, 'Inactivated Virus', NULL, NULL, NULL, NULL, NULL, NULL, '2025-05-29 20:43:24', '2025-05-29 20:43:24', 1);

-- --------------------------------------------------------

--
-- Table structure for table `vaccine_categories`
--

CREATE TABLE `vaccine_categories` (
  `category_id` int(11) NOT NULL,
  `category_name` varchar(100) NOT NULL COMMENT 'Name of the category (e.g., Childhood, Travel, Routine Adult)',
  `description` text DEFAULT NULL COMMENT 'Brief description of the category',
  `target_group` varchar(100) DEFAULT NULL COMMENT 'General target population',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `image_filename` varchar(255) DEFAULT NULL COMMENT 'Filename of the category image',
  `is_active` tinyint(1) DEFAULT 1 COMMENT 'Whether the category is currently in use'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `vaccine_categories`
--

INSERT INTO `vaccine_categories` (`category_id`, `category_name`, `description`, `target_group`, `created_at`, `updated_at`, `image_filename`, `is_active`) VALUES
(5, 'Childhood Immunizations', 'Routine vaccines recommended for infants and young children to protect against various serious diseases.', 'Infants and Children (0-18 years)', '2025-05-29 20:39:38', '2025-05-29 20:39:38', 'childhood_immunizations.png', 1),
(6, 'Adolescent & Adult Immunizations', 'Vaccines for pre-teens, teens, and adults, including boosters and specific adult-recommended vaccines.', 'Adolescents (11+ years) and Adults', '2025-05-29 20:39:38', '2025-05-29 22:46:43', 'cat_20250530014643508317_adult_vaccine.jpg', 1),
(7, 'Travel Vaccines', 'Vaccines recommended for international travelers based on destination, activities, and length of stay.', 'International Travelers', '2025-05-29 20:39:38', '2025-05-29 20:39:38', 'travel_vaccines.png', 1),
(8, 'General & Situational Vaccines', 'Vaccines that are widely recommended annually, or for specific situations like pregnancy or certain health conditions.', 'General Population, Pregnant Individuals, Specific Health Conditions', '2025-05-29 20:39:38', '2025-05-29 20:39:38', 'general_vaccines.png', 1);

--
-- Indexes for dumped tables
--

--
-- Indexes for table `admins`
--
ALTER TABLE `admins`
  ADD PRIMARY KEY (`user_id`);

--
-- Indexes for table `allergies`
--
ALTER TABLE `allergies`
  ADD PRIMARY KEY (`allergy_id`),
  ADD UNIQUE KEY `allergy_name_type_unique` (`allergy_name`,`allergy_type`);

--
-- Indexes for table `appointments`
--
ALTER TABLE `appointments`
  ADD PRIMARY KEY (`appointment_id`),
  ADD KEY `idx_appointments_patient` (`patient_id`),
  ADD KEY `idx_appointments_doctor` (`doctor_id`),
  ADD KEY `idx_appointments_datetime` (`appointment_date`,`start_time`),
  ADD KEY `idx_appointments_status` (`status`),
  ADD KEY `idx_appointments_doctor_location` (`doctor_location_id`),
  ADD KEY `appointments_creator_fk_idx` (`created_by`),
  ADD KEY `appointments_updater_fk_idx` (`updated_by`),
  ADD KEY `fk_appointment_type_idx` (`appointment_type_id`);

--
-- Indexes for table `appointment_followups`
--
ALTER TABLE `appointment_followups`
  ADD PRIMARY KEY (`followup_id`),
  ADD KEY `fk_followup_appointment_idx` (`appointment_id`),
  ADD KEY `fk_followup_updated_by_idx` (`updated_by`);

--
-- Indexes for table `appointment_types`
--
ALTER TABLE `appointment_types`
  ADD PRIMARY KEY (`type_id`),
  ADD UNIQUE KEY `type_name` (`type_name`);

--
-- Indexes for table `audit_log`
--
ALTER TABLE `audit_log`
  ADD PRIMARY KEY (`log_id`),
  ADD KEY `idx_audit_log_user` (`user_id`),
  ADD KEY `idx_audit_log_performer` (`performed_by_id`),
  ADD KEY `idx_audit_log_action_type` (`action_type`),
  ADD KEY `idx_audit_log_timestamp` (`performed_at`),
  ADD KEY `idx_audit_log_target` (`target_table`,`target_record_id`);

--
-- Indexes for table `chats`
--
ALTER TABLE `chats`
  ADD PRIMARY KEY (`chat_id`),
  ADD KEY `idx_chats_patient` (`patient_id`),
  ADD KEY `idx_chats_doctor` (`doctor_id`),
  ADD KEY `idx_chats_status` (`status`);

--
-- Indexes for table `chat_messages`
--
ALTER TABLE `chat_messages`
  ADD PRIMARY KEY (`message_id`),
  ADD KEY `idx_chat_messages_chat` (`chat_id`),
  ADD KEY `idx_chat_messages_sender` (`sender_type`,`sender_id`),
  ADD KEY `idx_chat_messages_sent` (`sent_at`),
  ADD KEY `idx_chat_messages_read` (`read_at`),
  ADD KEY `chat_messages_sender_fk_idx` (`sender_id`);
ALTER TABLE `chat_messages` ADD FULLTEXT KEY `idx_message_text` (`message_text`);

--
-- Indexes for table `conditions`
--
ALTER TABLE `conditions`
  ADD PRIMARY KEY (`condition_id`),
  ADD UNIQUE KEY `condition_name` (`condition_name`),
  ADD KEY `idx_conditions_urgency` (`urgency_level`),
  ADD KEY `idx_conditions_type` (`condition_type`),
  ADD KEY `idx_conditions_icd` (`icd_code`),
  ADD KEY `idx_conditions_active` (`is_active`),
  ADD KEY `fk_condition_testing_type_idx` (`testing_type_id`),
  ADD KEY `fk_condition_diagnosis_type_idx` (`diagnosis_type_id`),
  ADD KEY `fk_condition_department_idx` (`department_id`);

--
-- Indexes for table `departments`
--
ALTER TABLE `departments`
  ADD PRIMARY KEY (`department_id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `diagnoses`
--
ALTER TABLE `diagnoses`
  ADD PRIMARY KEY (`diagnosis_id`),
  ADD KEY `idx_diagnoses_patient` (`patient_id`),
  ADD KEY `idx_diagnoses_doctor` (`doctor_id`),
  ADD KEY `idx_diagnoses_code` (`diagnosis_code`),
  ADD KEY `idx_diagnoses_date` (`diagnosis_date`),
  ADD KEY `diagnoses_creator_fk_idx` (`created_by`),
  ADD KEY `diagnoses_updater_fk_idx` (`updated_by`);

--
-- Indexes for table `diagnosis_types`
--
ALTER TABLE `diagnosis_types`
  ADD PRIMARY KEY (`diagnosis_type_id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `diet_plans`
--
ALTER TABLE `diet_plans`
  ADD PRIMARY KEY (`plan_id`),
  ADD KEY `idx_diet_plans_creator` (`creator_id`),
  ADD KEY `idx_diet_plans_type` (`plan_type`),
  ADD KEY `idx_diet_plans_public` (`is_public`),
  ADD KEY `diet_plans_updater_fk_idx` (`updated_by`);

--
-- Indexes for table `diet_plan_food_items`
--
ALTER TABLE `diet_plan_food_items`
  ADD PRIMARY KEY (`item_id`),
  ADD KEY `idx_diet_plan_food_meal` (`meal_id`);

--
-- Indexes for table `diet_plan_meals`
--
ALTER TABLE `diet_plan_meals`
  ADD PRIMARY KEY (`meal_id`),
  ADD KEY `idx_diet_plan_meals_plan` (`plan_id`),
  ADD KEY `idx_diet_plan_meals_type` (`meal_type`);

--
-- Indexes for table `doctors`
--
ALTER TABLE `doctors`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `npi_number` (`npi_number`),
  ADD KEY `fk_doctor_specialization_idx` (`specialization_id`),
  ADD KEY `fk_doctor_department_idx` (`department_id`);

--
-- Indexes for table `doctor_availability_overrides`
--
ALTER TABLE `doctor_availability_overrides`
  ADD PRIMARY KEY (`override_id`),
  ADD UNIQUE KEY `uq_override_entry` (`doctor_id`,`doctor_location_id`,`override_date`,`start_time`,`end_time`),
  ADD KEY `idx_override_doctor_date` (`doctor_id`,`override_date`),
  ADD KEY `idx_override_doc_loc_date` (`doctor_id`,`doctor_location_id`,`override_date`),
  ADD KEY `fk_override_doctor_location_idx` (`doctor_location_id`);

--
-- Indexes for table `doctor_documents`
--
ALTER TABLE `doctor_documents`
  ADD PRIMARY KEY (`document_id`),
  ADD KEY `fk_doc_docs_doctor_idx` (`doctor_id`);

--
-- Indexes for table `doctor_locations`
--
ALTER TABLE `doctor_locations`
  ADD PRIMARY KEY (`doctor_location_id`),
  ADD KEY `idx_docloc_doctor` (`doctor_id`),
  ADD KEY `idx_docloc_name` (`doctor_id`,`location_name`);

--
-- Indexes for table `doctor_location_availability`
--
ALTER TABLE `doctor_location_availability`
  ADD PRIMARY KEY (`location_availability_id`),
  ADD UNIQUE KEY `uq_doctor_location_time_slot` (`doctor_location_id`,`day_of_week`,`start_time`,`end_time`),
  ADD KEY `idx_dla_doctor_location` (`doctor_location_id`),
  ADD KEY `idx_dla_day_time` (`day_of_week`,`start_time`,`end_time`);

--
-- Indexes for table `doctor_location_daily_caps`
--
ALTER TABLE `doctor_location_daily_caps`
  ADD PRIMARY KEY (`cap_id`),
  ADD UNIQUE KEY `uq_doctor_location_day_cap` (`doctor_id`,`doctor_location_id`,`day_of_week`),
  ADD KEY `doctor_location_id` (`doctor_location_id`);

--
-- Indexes for table `doctor_reviews`
--
ALTER TABLE `doctor_reviews`
  ADD PRIMARY KEY (`review_id`),
  ADD KEY `fk_doc_reviews_doctor_idx` (`doctor_id`),
  ADD KEY `fk_doc_reviews_reviewer_idx` (`reviewer_id`);

--
-- Indexes for table `food_item_library`
--
ALTER TABLE `food_item_library`
  ADD PRIMARY KEY (`food_item_id`),
  ADD UNIQUE KEY `item_name` (`item_name`),
  ADD KEY `creator_id` (`creator_id`),
  ADD KEY `idx_food_item_library_name` (`item_name`);

--
-- Indexes for table `insurance_providers`
--
ALTER TABLE `insurance_providers`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `provider_name` (`provider_name`);

--
-- Indexes for table `message_attachments`
--
ALTER TABLE `message_attachments`
  ADD PRIMARY KEY (`attachment_id`),
  ADD KEY `idx_attachment_message` (`message_id`),
  ADD KEY `idx_attachment_type` (`file_type`);

--
-- Indexes for table `patients`
--
ALTER TABLE `patients`
  ADD PRIMARY KEY (`user_id`),
  ADD KEY `fk_patients_insurance_provider_idx` (`insurance_provider_id`);

--
-- Indexes for table `patient_allergies`
--
ALTER TABLE `patient_allergies`
  ADD PRIMARY KEY (`patient_id`,`allergy_id`),
  ADD KEY `idx_patient_allergies_severity` (`severity`),
  ADD KEY `patient_allergies_allergy_fk_idx` (`allergy_id`);

--
-- Indexes for table `patient_medical_reports`
--
ALTER TABLE `patient_medical_reports`
  ADD PRIMARY KEY (`report_id`),
  ADD KEY `idx_patient_medical_reports_patient_id` (`patient_id`),
  ADD KEY `idx_patient_medical_reports_submission_date` (`submission_date`),
  ADD KEY `idx_patient_medical_reports_document_type` (`document_type`);

--
-- Indexes for table `patient_symptoms`
--
ALTER TABLE `patient_symptoms`
  ADD PRIMARY KEY (`patient_symptom_id`),
  ADD KEY `idx_patient_symptoms_patient` (`patient_id`),
  ADD KEY `idx_patient_symptoms_symptom` (`symptom_id`),
  ADD KEY `idx_patient_symptoms_date` (`reported_date`),
  ADD KEY `patient_symptoms_reporter_fk_idx` (`reported_by`);

--
-- Indexes for table `patient_vaccinations`
--
ALTER TABLE `patient_vaccinations`
  ADD PRIMARY KEY (`patient_vaccination_id`),
  ADD KEY `patient_id` (`patient_id`),
  ADD KEY `vaccine_id` (`vaccine_id`),
  ADD KEY `administered_by_id` (`administered_by_id`);

--
-- Indexes for table `pending_registrations`
--
ALTER TABLE `pending_registrations`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `email` (`email`),
  ADD UNIQUE KEY `username` (`username`),
  ADD KEY `idx_pending_reg_spec` (`specialization_id`),
  ADD KEY `fk_pending_reg_user_idx` (`user_id`),
  ADD KEY `fk_pending_reg_processed_by_idx` (`processed_by`);

--
-- Indexes for table `specializations`
--
ALTER TABLE `specializations`
  ADD PRIMARY KEY (`specialization_id`),
  ADD UNIQUE KEY `name` (`name`),
  ADD KEY `idx_specialization_name` (`name`),
  ADD KEY `idx_specialization_department` (`department_id`);

--
-- Indexes for table `symptoms`
--
ALTER TABLE `symptoms`
  ADD PRIMARY KEY (`symptom_id`),
  ADD UNIQUE KEY `symptom_name` (`symptom_name`),
  ADD KEY `idx_symptoms_area` (`body_area`),
  ADD KEY `idx_symptoms_icd` (`icd_code`),
  ADD KEY `idx_symptoms_category` (`symptom_category`);

--
-- Indexes for table `testing_types`
--
ALTER TABLE `testing_types`
  ADD PRIMARY KEY (`testing_type_id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `username` (`username`),
  ADD UNIQUE KEY `email` (`email`);

--
-- Indexes for table `user_diet_plans`
--
ALTER TABLE `user_diet_plans`
  ADD PRIMARY KEY (`user_diet_plan_id`),
  ADD KEY `idx_user_diet_plans_user_id` (`user_id`),
  ADD KEY `idx_user_diet_plans_plan_id` (`plan_id`),
  ADD KEY `idx_user_diet_plans_dates` (`start_date`,`end_date`),
  ADD KEY `idx_user_diet_plans_active` (`active`),
  ADD KEY `user_diet_plans_assigner_fk_idx` (`assigned_by`);

--
-- Indexes for table `vaccines`
--
ALTER TABLE `vaccines`
  ADD PRIMARY KEY (`vaccine_id`),
  ADD UNIQUE KEY `abbreviation_UNIQUE` (`abbreviation`),
  ADD KEY `fk_vaccines_category_idx` (`category_id`);

--
-- Indexes for table `vaccine_categories`
--
ALTER TABLE `vaccine_categories`
  ADD PRIMARY KEY (`category_id`),
  ADD UNIQUE KEY `category_name_UNIQUE` (`category_name`),
  ADD UNIQUE KEY `uk_category_name` (`category_name`),
  ADD KEY `idx_vaccine_category_name` (`category_name`),
  ADD KEY `idx_vaccine_category_active` (`is_active`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `allergies`
--
ALTER TABLE `allergies`
  MODIFY `allergy_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=32;

--
-- AUTO_INCREMENT for table `appointments`
--
ALTER TABLE `appointments`
  MODIFY `appointment_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=26;

--
-- AUTO_INCREMENT for table `appointment_followups`
--
ALTER TABLE `appointment_followups`
  MODIFY `followup_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `appointment_types`
--
ALTER TABLE `appointment_types`
  MODIFY `type_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT for table `audit_log`
--
ALTER TABLE `audit_log`
  MODIFY `log_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=20;

--
-- AUTO_INCREMENT for table `chats`
--
ALTER TABLE `chats`
  MODIFY `chat_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT for table `chat_messages`
--
ALTER TABLE `chat_messages`
  MODIFY `message_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `conditions`
--
ALTER TABLE `conditions`
  MODIFY `condition_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=129;

--
-- AUTO_INCREMENT for table `departments`
--
ALTER TABLE `departments`
  MODIFY `department_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=23;

--
-- AUTO_INCREMENT for table `diagnoses`
--
ALTER TABLE `diagnoses`
  MODIFY `diagnosis_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=6;

--
-- AUTO_INCREMENT for table `diagnosis_types`
--
ALTER TABLE `diagnosis_types`
  MODIFY `diagnosis_type_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `diet_plans`
--
ALTER TABLE `diet_plans`
  MODIFY `plan_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- AUTO_INCREMENT for table `diet_plan_food_items`
--
ALTER TABLE `diet_plan_food_items`
  MODIFY `item_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=49;

--
-- AUTO_INCREMENT for table `diet_plan_meals`
--
ALTER TABLE `diet_plan_meals`
  MODIFY `meal_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=16;

--
-- AUTO_INCREMENT for table `doctor_availability_overrides`
--
ALTER TABLE `doctor_availability_overrides`
  MODIFY `override_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `doctor_documents`
--
ALTER TABLE `doctor_documents`
  MODIFY `document_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `doctor_locations`
--
ALTER TABLE `doctor_locations`
  MODIFY `doctor_location_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT for table `doctor_location_availability`
--
ALTER TABLE `doctor_location_availability`
  MODIFY `location_availability_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT for table `doctor_location_daily_caps`
--
ALTER TABLE `doctor_location_daily_caps`
  MODIFY `cap_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `doctor_reviews`
--
ALTER TABLE `doctor_reviews`
  MODIFY `review_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `food_item_library`
--
ALTER TABLE `food_item_library`
  MODIFY `food_item_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=58;

--
-- AUTO_INCREMENT for table `insurance_providers`
--
ALTER TABLE `insurance_providers`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=8;

--
-- AUTO_INCREMENT for table `message_attachments`
--
ALTER TABLE `message_attachments`
  MODIFY `attachment_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `patient_medical_reports`
--
ALTER TABLE `patient_medical_reports`
  MODIFY `report_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `patient_symptoms`
--
ALTER TABLE `patient_symptoms`
  MODIFY `patient_symptom_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `patient_vaccinations`
--
ALTER TABLE `patient_vaccinations`
  MODIFY `patient_vaccination_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT for table `pending_registrations`
--
ALTER TABLE `pending_registrations`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `specializations`
--
ALTER TABLE `specializations`
  MODIFY `specialization_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=22;

--
-- AUTO_INCREMENT for table `symptoms`
--
ALTER TABLE `symptoms`
  MODIFY `symptom_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=11;

--
-- AUTO_INCREMENT for table `testing_types`
--
ALTER TABLE `testing_types`
  MODIFY `testing_type_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=23;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `user_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=57;

--
-- AUTO_INCREMENT for table `user_diet_plans`
--
ALTER TABLE `user_diet_plans`
  MODIFY `user_diet_plan_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `vaccines`
--
ALTER TABLE `vaccines`
  MODIFY `vaccine_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=72;

--
-- AUTO_INCREMENT for table `vaccine_categories`
--
ALTER TABLE `vaccine_categories`
  MODIFY `category_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=13;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `admins`
--
ALTER TABLE `admins`
  ADD CONSTRAINT `fk_admins_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `appointments`
--
ALTER TABLE `appointments`
  ADD CONSTRAINT `fk_appointments_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE NO ACTION,
  ADD CONSTRAINT `fk_appointments_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_appointments_doctor_location` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_appointments_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_appointments_type` FOREIGN KEY (`appointment_type_id`) REFERENCES `appointment_types` (`type_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_appointments_updater` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `appointment_followups`
--
ALTER TABLE `appointment_followups`
  ADD CONSTRAINT `fk_followup_appointment` FOREIGN KEY (`appointment_id`) REFERENCES `appointments` (`appointment_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_followup_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `audit_log`
--
ALTER TABLE `audit_log`
  ADD CONSTRAINT `fk_audit_log_performer` FOREIGN KEY (`performed_by_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_audit_log_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `chats`
--
ALTER TABLE `chats`
  ADD CONSTRAINT `fk_chats_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_chats_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `chat_messages`
--
ALTER TABLE `chat_messages`
  ADD CONSTRAINT `fk_chat_messages_chat` FOREIGN KEY (`chat_id`) REFERENCES `chats` (`chat_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_chat_messages_sender` FOREIGN KEY (`sender_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `conditions`
--
ALTER TABLE `conditions`
  ADD CONSTRAINT `fk_conditions_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`department_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_conditions_diagnosis_type` FOREIGN KEY (`diagnosis_type_id`) REFERENCES `diagnosis_types` (`diagnosis_type_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_conditions_testing_type` FOREIGN KEY (`testing_type_id`) REFERENCES `testing_types` (`testing_type_id`) ON DELETE SET NULL ON UPDATE CASCADE;

--
-- Constraints for table `diagnoses`
--
ALTER TABLE `diagnoses`
  ADD CONSTRAINT `fk_diagnoses_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE NO ACTION,
  ADD CONSTRAINT `fk_diagnoses_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_diagnoses_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_diagnoses_updater` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `diet_plans`
--
ALTER TABLE `diet_plans`
  ADD CONSTRAINT `fk_dp_creator` FOREIGN KEY (`creator_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_dp_updater` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `diet_plan_meals`
--
ALTER TABLE `diet_plan_meals`
  ADD CONSTRAINT `fk_dpm_plan` FOREIGN KEY (`plan_id`) REFERENCES `diet_plans` (`plan_id`) ON DELETE CASCADE;

--
-- Constraints for table `doctors`
--
ALTER TABLE `doctors`
  ADD CONSTRAINT `fk_doctors_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`department_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_doctors_specialization` FOREIGN KEY (`specialization_id`) REFERENCES `specializations` (`specialization_id`) ON DELETE NO ACTION,
  ADD CONSTRAINT `fk_doctors_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `doctor_availability_overrides`
--
ALTER TABLE `doctor_availability_overrides`
  ADD CONSTRAINT `fk_dao_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_dao_doctor_location` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE SET NULL;

--
-- Constraints for table `doctor_documents`
--
ALTER TABLE `doctor_documents`
  ADD CONSTRAINT `fk_dd_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `doctor_locations`
--
ALTER TABLE `doctor_locations`
  ADD CONSTRAINT `fk_dl_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `doctor_location_availability`
--
ALTER TABLE `doctor_location_availability`
  ADD CONSTRAINT `fk_dla_doctor_location` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE CASCADE;

--
-- Constraints for table `doctor_location_daily_caps`
--
ALTER TABLE `doctor_location_daily_caps`
  ADD CONSTRAINT `doctor_location_daily_caps_ibfk_1` FOREIGN KEY (`doctor_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `doctor_location_daily_caps_ibfk_2` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE CASCADE;

--
-- Constraints for table `doctor_reviews`
--
ALTER TABLE `doctor_reviews`
  ADD CONSTRAINT `fk_dr_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_dr_reviewer` FOREIGN KEY (`reviewer_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `food_item_library`
--
ALTER TABLE `food_item_library`
  ADD CONSTRAINT `food_item_library_ibfk_1` FOREIGN KEY (`creator_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `message_attachments`
--
ALTER TABLE `message_attachments`
  ADD CONSTRAINT `fk_ma_message` FOREIGN KEY (`message_id`) REFERENCES `chat_messages` (`message_id`) ON DELETE CASCADE;

--
-- Constraints for table `patients`
--
ALTER TABLE `patients`
  ADD CONSTRAINT `fk_patients_insurance_provider` FOREIGN KEY (`insurance_provider_id`) REFERENCES `insurance_providers` (`id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_patients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `patient_allergies`
--
ALTER TABLE `patient_allergies`
  ADD CONSTRAINT `fk_pa_allergy` FOREIGN KEY (`allergy_id`) REFERENCES `allergies` (`allergy_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_pa_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `patient_medical_reports`
--
ALTER TABLE `patient_medical_reports`
  ADD CONSTRAINT `patient_medical_reports_ibfk_1` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `patient_symptoms`
--
ALTER TABLE `patient_symptoms`
  ADD CONSTRAINT `fk_ps_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_ps_reporter` FOREIGN KEY (`reported_by`) REFERENCES `users` (`user_id`) ON DELETE NO ACTION,
  ADD CONSTRAINT `fk_ps_symptom` FOREIGN KEY (`symptom_id`) REFERENCES `symptoms` (`symptom_id`) ON DELETE CASCADE;

--
-- Constraints for table `patient_vaccinations`
--
ALTER TABLE `patient_vaccinations`
  ADD CONSTRAINT `patient_vaccinations_ibfk_1` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `patient_vaccinations_ibfk_2` FOREIGN KEY (`vaccine_id`) REFERENCES `vaccines` (`vaccine_id`),
  ADD CONSTRAINT `patient_vaccinations_ibfk_3` FOREIGN KEY (`administered_by_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `pending_registrations`
--
ALTER TABLE `pending_registrations`
  ADD CONSTRAINT `fk_pr_processed_by` FOREIGN KEY (`processed_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_pr_specialization` FOREIGN KEY (`specialization_id`) REFERENCES `specializations` (`specialization_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_pr_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;

--
-- Constraints for table `specializations`
--
ALTER TABLE `specializations`
  ADD CONSTRAINT `fk_specialization_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`department_id`) ON DELETE SET NULL ON UPDATE CASCADE;

--
-- Constraints for table `user_diet_plans`
--
ALTER TABLE `user_diet_plans`
  ADD CONSTRAINT `fk_udp_assigner` FOREIGN KEY (`assigned_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  ADD CONSTRAINT `fk_udp_plan` FOREIGN KEY (`plan_id`) REFERENCES `diet_plans` (`plan_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_udp_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `vaccines`
--
ALTER TABLE `vaccines`
  ADD CONSTRAINT `fk_vaccines_category` FOREIGN KEY (`category_id`) REFERENCES `vaccine_categories` (`category_id`) ON UPDATE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
