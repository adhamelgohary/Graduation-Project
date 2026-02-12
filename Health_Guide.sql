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
-- Indexes for dumped tables
--

ALTER TABLE `admins` ADD PRIMARY KEY (`user_id`);
ALTER TABLE `allergies` ADD PRIMARY KEY (`allergy_id`), ADD UNIQUE KEY `allergy_name_type_unique` (`allergy_name`,`allergy_type`);
ALTER TABLE `appointments` ADD PRIMARY KEY (`appointment_id`), ADD KEY `idx_appointments_patient` (`patient_id`), ADD KEY `idx_appointments_doctor` (`doctor_id`), ADD KEY `idx_appointments_datetime` (`appointment_date`,`start_time`), ADD KEY `idx_appointments_status` (`status`), ADD KEY `idx_appointments_doctor_location` (`doctor_location_id`), ADD KEY `appointments_creator_fk_idx` (`created_by`), ADD KEY `appointments_updater_fk_idx` (`updated_by`), ADD KEY `fk_appointment_type_idx` (`appointment_type_id`);
ALTER TABLE `appointment_followups` ADD PRIMARY KEY (`followup_id`), ADD KEY `fk_followup_appointment_idx` (`appointment_id`), ADD KEY `fk_followup_updated_by_idx` (`updated_by`);
ALTER TABLE `appointment_types` ADD PRIMARY KEY (`type_id`), ADD UNIQUE KEY `type_name` (`type_name`);
ALTER TABLE `audit_log` ADD PRIMARY KEY (`log_id`), ADD KEY `idx_audit_log_user` (`user_id`), ADD KEY `idx_audit_log_performer` (`performed_by_id`), ADD KEY `idx_audit_log_action_type` (`action_type`), ADD KEY `idx_audit_log_timestamp` (`performed_at`), ADD KEY `idx_audit_log_target` (`target_table`,`target_record_id`);
ALTER TABLE `chats` ADD PRIMARY KEY (`chat_id`), ADD KEY `idx_chats_patient` (`patient_id`), ADD KEY `idx_chats_doctor` (`doctor_id`), ADD KEY `idx_chats_status` (`status`);
ALTER TABLE `chat_messages` ADD PRIMARY KEY (`message_id`), ADD KEY `idx_chat_messages_chat` (`chat_id`), ADD KEY `idx_chat_messages_sender` (`sender_type`,`sender_id`), ADD KEY `idx_chat_messages_sent` (`sent_at`), ADD KEY `idx_chat_messages_read` (`read_at`), ADD KEY `chat_messages_sender_fk_idx` (`sender_id`);
ALTER TABLE `chat_messages` ADD FULLTEXT KEY `idx_message_text` (`message_text`);
ALTER TABLE `conditions` ADD PRIMARY KEY (`condition_id`), ADD UNIQUE KEY `condition_name` (`condition_name`), ADD KEY `idx_conditions_urgency` (`urgency_level`), ADD KEY `idx_conditions_type` (`condition_type`), ADD KEY `idx_conditions_icd` (`icd_code`), ADD KEY `idx_conditions_active` (`is_active`), ADD KEY `fk_condition_testing_type_idx` (`testing_type_id`), ADD KEY `fk_condition_diagnosis_type_idx` (`diagnosis_type_id`), ADD KEY `fk_condition_department_idx` (`department_id`);
ALTER TABLE `departments` ADD PRIMARY KEY (`department_id`), ADD UNIQUE KEY `name` (`name`);
ALTER TABLE `diagnoses` ADD PRIMARY KEY (`diagnosis_id`), ADD KEY `idx_diagnoses_patient` (`patient_id`), ADD KEY `idx_diagnoses_doctor` (`doctor_id`), ADD KEY `idx_diagnoses_code` (`diagnosis_code`), ADD KEY `idx_diagnoses_date` (`diagnosis_date`), ADD KEY `diagnoses_creator_fk_idx` (`created_by`), ADD KEY `diagnoses_updater_fk_idx` (`updated_by`);
ALTER TABLE `diagnosis_types` ADD PRIMARY KEY (`diagnosis_type_id`), ADD UNIQUE KEY `name` (`name`);
ALTER TABLE `diet_plans` ADD PRIMARY KEY (`plan_id`), ADD KEY `idx_diet_plans_creator` (`creator_id`), ADD KEY `idx_diet_plans_type` (`plan_type`), ADD KEY `idx_diet_plans_public` (`is_public`), ADD KEY `diet_plans_updater_fk_idx` (`updated_by`);
ALTER TABLE `diet_plan_food_items` ADD PRIMARY KEY (`item_id`), ADD KEY `idx_diet_plan_food_meal` (`meal_id`);
ALTER TABLE `diet_plan_meals` ADD PRIMARY KEY (`meal_id`), ADD KEY `idx_diet_plan_meals_plan` (`plan_id`), ADD KEY `idx_diet_plan_meals_type` (`meal_type`);
ALTER TABLE `doctors` ADD PRIMARY KEY (`user_id`), ADD UNIQUE KEY `npi_number` (`npi_number`), ADD KEY `fk_doctor_specialization_idx` (`specialization_id`), ADD KEY `fk_doctor_department_idx` (`department_id`);
ALTER TABLE `doctor_availability_overrides` ADD PRIMARY KEY (`override_id`), ADD UNIQUE KEY `uq_override_entry` (`doctor_id`,`doctor_location_id`,`override_date`,`start_time`,`end_time`), ADD KEY `idx_override_doctor_date` (`doctor_id`,`override_date`), ADD KEY `idx_override_doc_loc_date` (`doctor_id`,`doctor_location_id`,`override_date`), ADD KEY `fk_override_doctor_location_idx` (`doctor_location_id`);
ALTER TABLE `doctor_documents` ADD PRIMARY KEY (`document_id`), ADD KEY `fk_doc_docs_doctor_idx` (`doctor_id`);
ALTER TABLE `doctor_locations` ADD PRIMARY KEY (`doctor_location_id`), ADD KEY `idx_docloc_doctor` (`doctor_id`), ADD KEY `idx_docloc_name` (`doctor_id`,`location_name`);
ALTER TABLE `doctor_location_availability` ADD PRIMARY KEY (`location_availability_id`), ADD UNIQUE KEY `uq_doctor_location_time_slot` (`doctor_location_id`,`day_of_week`,`start_time`,`end_time`), ADD KEY `idx_dla_doctor_location` (`doctor_location_id`), ADD KEY `idx_dla_day_time` (`day_of_week`,`start_time`,`end_time`);
ALTER TABLE `doctor_location_daily_caps` ADD PRIMARY KEY (`cap_id`), ADD UNIQUE KEY `uq_doctor_location_day_cap` (`doctor_id`,`doctor_location_id`,`day_of_week`), ADD KEY `doctor_location_id` (`doctor_location_id`);
ALTER TABLE `doctor_reviews` ADD PRIMARY KEY (`review_id`), ADD KEY `fk_doc_reviews_doctor_idx` (`doctor_id`), ADD KEY `fk_doc_reviews_reviewer_idx` (`reviewer_id`);
ALTER TABLE `food_item_library` ADD PRIMARY KEY (`food_item_id`), ADD UNIQUE KEY `item_name` (`item_name`), ADD KEY `creator_id` (`creator_id`), ADD KEY `idx_food_item_library_name` (`item_name`);
ALTER TABLE `insurance_providers` ADD PRIMARY KEY (`id`), ADD UNIQUE KEY `provider_name` (`provider_name`);
ALTER TABLE `message_attachments` ADD PRIMARY KEY (`attachment_id`), ADD KEY `idx_attachment_message` (`message_id`), ADD KEY `idx_attachment_type` (`file_type`);
ALTER TABLE `patients` ADD PRIMARY KEY (`user_id`), ADD KEY `fk_patients_insurance_provider_idx` (`insurance_provider_id`);
ALTER TABLE `patient_allergies` ADD PRIMARY KEY (`patient_id`,`allergy_id`), ADD KEY `idx_patient_allergies_severity` (`severity`), ADD KEY `patient_allergies_allergy_fk_idx` (`allergy_id`);
ALTER TABLE `patient_medical_reports` ADD PRIMARY KEY (`report_id`), ADD KEY `idx_patient_medical_reports_patient_id` (`patient_id`), ADD KEY `idx_patient_medical_reports_submission_date` (`submission_date`), ADD KEY `idx_patient_medical_reports_document_type` (`document_type`);
ALTER TABLE `patient_symptoms` ADD PRIMARY KEY (`patient_symptom_id`), ADD KEY `idx_patient_symptoms_patient` (`patient_id`), ADD KEY `idx_patient_symptoms_symptom` (`symptom_id`), ADD KEY `idx_patient_symptoms_date` (`reported_date`), ADD KEY `patient_symptoms_reporter_fk_idx` (`reported_by`);
ALTER TABLE `patient_vaccinations` ADD PRIMARY KEY (`patient_vaccination_id`), ADD KEY `patient_id` (`patient_id`), ADD KEY `vaccine_id` (`vaccine_id`), ADD KEY `administered_by_id` (`administered_by_id`);
ALTER TABLE `pending_registrations` ADD PRIMARY KEY (`id`), ADD UNIQUE KEY `email` (`email`), ADD UNIQUE KEY `username` (`username`), ADD KEY `idx_pending_reg_spec` (`specialization_id`), ADD KEY `fk_pending_reg_user_idx` (`user_id`), ADD KEY `fk_pending_reg_processed_by_idx` (`processed_by`);
ALTER TABLE `specializations` ADD PRIMARY KEY (`specialization_id`), ADD UNIQUE KEY `name` (`name`), ADD KEY `idx_specialization_name` (`name`), ADD KEY `idx_specialization_department` (`department_id`);
ALTER TABLE `symptoms` ADD PRIMARY KEY (`symptom_id`), ADD UNIQUE KEY `symptom_name` (`symptom_name`), ADD KEY `idx_symptoms_area` (`body_area`), ADD KEY `idx_symptoms_icd` (`icd_code`), ADD KEY `idx_symptoms_category` (`symptom_category`);
ALTER TABLE `testing_types` ADD PRIMARY KEY (`testing_type_id`), ADD UNIQUE KEY `name` (`name`);
ALTER TABLE `users` ADD PRIMARY KEY (`user_id`), ADD UNIQUE KEY `username` (`username`), ADD UNIQUE KEY `email` (`email`);
ALTER TABLE `user_diet_plans` ADD PRIMARY KEY (`user_diet_plan_id`), ADD KEY `idx_user_diet_plans_user_id` (`user_id`), ADD KEY `idx_user_diet_plans_plan_id` (`plan_id`), ADD KEY `idx_user_diet_plans_dates` (`start_date`,`end_date`), ADD KEY `idx_user_diet_plans_active` (`active`), ADD KEY `user_diet_plans_assigner_fk_idx` (`assigned_by`);
ALTER TABLE `vaccines` ADD PRIMARY KEY (`vaccine_id`), ADD UNIQUE KEY `abbreviation_UNIQUE` (`abbreviation`), ADD KEY `fk_vaccines_category_idx` (`category_id`);
ALTER TABLE `vaccine_categories` ADD PRIMARY KEY (`category_id`), ADD UNIQUE KEY `category_name_UNIQUE` (`category_name`), ADD UNIQUE KEY `uk_category_name` (`category_name`), ADD KEY `idx_vaccine_category_name` (`category_name`), ADD KEY `idx_vaccine_category_active` (`is_active`);

--
-- AUTO_INCREMENT for dumped tables
--

ALTER TABLE `allergies` MODIFY `allergy_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `appointments` MODIFY `appointment_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `appointment_followups` MODIFY `followup_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `appointment_types` MODIFY `type_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `audit_log` MODIFY `log_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `chats` MODIFY `chat_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `chat_messages` MODIFY `message_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `conditions` MODIFY `condition_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `departments` MODIFY `department_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `diagnoses` MODIFY `diagnosis_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `diagnosis_types` MODIFY `diagnosis_type_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `diet_plans` MODIFY `plan_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `diet_plan_food_items` MODIFY `item_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `diet_plan_meals` MODIFY `meal_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `doctor_availability_overrides` MODIFY `override_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `doctor_documents` MODIFY `document_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `doctor_locations` MODIFY `doctor_location_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `doctor_location_availability` MODIFY `location_availability_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `doctor_location_daily_caps` MODIFY `cap_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `doctor_reviews` MODIFY `review_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `food_item_library` MODIFY `food_item_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `insurance_providers` MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `message_attachments` MODIFY `attachment_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `patient_medical_reports` MODIFY `report_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `patient_symptoms` MODIFY `patient_symptom_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `patient_vaccinations` MODIFY `patient_vaccination_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `pending_registrations` MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `specializations` MODIFY `specialization_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `symptoms` MODIFY `symptom_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `testing_types` MODIFY `testing_type_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `users` MODIFY `user_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `user_diet_plans` MODIFY `user_diet_plan_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `vaccines` MODIFY `vaccine_id` int(11) NOT NULL AUTO_INCREMENT;
ALTER TABLE `vaccine_categories` MODIFY `category_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- Constraints for dumped tables
--

ALTER TABLE `admins` ADD CONSTRAINT `fk_admins_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `appointments` ADD CONSTRAINT `fk_appointments_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE NO ACTION, ADD CONSTRAINT `fk_appointments_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_appointments_doctor_location` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_appointments_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_appointments_type` FOREIGN KEY (`appointment_type_id`) REFERENCES `appointment_types` (`type_id`) ON DELETE SET NULL ON UPDATE CASCADE, ADD CONSTRAINT `fk_appointments_updater` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `appointment_followups` ADD CONSTRAINT `fk_followup_appointment` FOREIGN KEY (`appointment_id`) REFERENCES `appointments` (`appointment_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_followup_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `audit_log` ADD CONSTRAINT `fk_audit_log_performer` FOREIGN KEY (`performed_by_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_audit_log_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `chats` ADD CONSTRAINT `fk_chats_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_chats_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `chat_messages` ADD CONSTRAINT `fk_chat_messages_chat` FOREIGN KEY (`chat_id`) REFERENCES `chats` (`chat_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_chat_messages_sender` FOREIGN KEY (`sender_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `conditions` ADD CONSTRAINT `fk_conditions_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`department_id`) ON DELETE SET NULL ON UPDATE CASCADE, ADD CONSTRAINT `fk_conditions_diagnosis_type` FOREIGN KEY (`diagnosis_type_id`) REFERENCES `diagnosis_types` (`diagnosis_type_id`) ON DELETE SET NULL ON UPDATE CASCADE, ADD CONSTRAINT `fk_conditions_testing_type` FOREIGN KEY (`testing_type_id`) REFERENCES `testing_types` (`testing_type_id`) ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE `diagnoses` ADD CONSTRAINT `fk_diagnoses_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE NO ACTION, ADD CONSTRAINT `fk_diagnoses_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_diagnoses_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_diagnoses_updater` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `diet_plans` ADD CONSTRAINT `fk_dp_creator` FOREIGN KEY (`creator_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_dp_updater` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `diet_plan_meals` ADD CONSTRAINT `fk_dpm_plan` FOREIGN KEY (`plan_id`) REFERENCES `diet_plans` (`plan_id`) ON DELETE CASCADE;
ALTER TABLE `doctors` ADD CONSTRAINT `fk_doctors_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`department_id`) ON DELETE SET NULL ON UPDATE CASCADE, ADD CONSTRAINT `fk_doctors_specialization` FOREIGN KEY (`specialization_id`) REFERENCES `specializations` (`specialization_id`) ON DELETE NO ACTION, ADD CONSTRAINT `fk_doctors_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `doctor_availability_overrides` ADD CONSTRAINT `fk_dao_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_dao_doctor_location` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE SET NULL;
ALTER TABLE `doctor_documents` ADD CONSTRAINT `fk_dd_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `doctor_locations` ADD CONSTRAINT `fk_dl_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `doctor_location_availability` ADD CONSTRAINT `fk_dla_doctor_location` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE CASCADE;
ALTER TABLE `doctor_location_daily_caps` ADD CONSTRAINT `doctor_location_daily_caps_ibfk_1` FOREIGN KEY (`doctor_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `doctor_location_daily_caps_ibfk_2` FOREIGN KEY (`doctor_location_id`) REFERENCES `doctor_locations` (`doctor_location_id`) ON DELETE CASCADE;
ALTER TABLE `doctor_reviews` ADD CONSTRAINT `fk_dr_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `doctors` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_dr_reviewer` FOREIGN KEY (`reviewer_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `food_item_library` ADD CONSTRAINT `food_item_library_ibfk_1` FOREIGN KEY (`creator_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `message_attachments` ADD CONSTRAINT `fk_ma_message` FOREIGN KEY (`message_id`) REFERENCES `chat_messages` (`message_id`) ON DELETE CASCADE;
ALTER TABLE `patients` ADD CONSTRAINT `fk_patients_insurance_provider` FOREIGN KEY (`insurance_provider_id`) REFERENCES `insurance_providers` (`id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_patients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `patient_allergies` ADD CONSTRAINT `fk_pa_allergy` FOREIGN KEY (`allergy_id`) REFERENCES `allergies` (`allergy_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_pa_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `patient_medical_reports` ADD CONSTRAINT `patient_medical_reports_ibfk_1` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `patient_symptoms` ADD CONSTRAINT `fk_ps_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_ps_reporter` FOREIGN KEY (`reported_by`) REFERENCES `users` (`user_id`) ON DELETE NO ACTION, ADD CONSTRAINT `fk_ps_symptom` FOREIGN KEY (`symptom_id`) REFERENCES `symptoms` (`symptom_id`) ON DELETE CASCADE;
ALTER TABLE `patient_vaccinations` ADD CONSTRAINT `patient_vaccinations_ibfk_1` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`user_id`) ON DELETE CASCADE, ADD CONSTRAINT `patient_vaccinations_ibfk_2` FOREIGN KEY (`vaccine_id`) REFERENCES `vaccines` (`vaccine_id`), ADD CONSTRAINT `patient_vaccinations_ibfk_3` FOREIGN KEY (`administered_by_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `pending_registrations` ADD CONSTRAINT `fk_pr_processed_by` FOREIGN KEY (`processed_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_pr_specialization` FOREIGN KEY (`specialization_id`) REFERENCES `specializations` (`specialization_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_pr_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `specializations` ADD CONSTRAINT `fk_specialization_department` FOREIGN KEY (`department_id`) REFERENCES `departments` (`department_id`) ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE `user_diet_plans` ADD CONSTRAINT `fk_udp_assigner` FOREIGN KEY (`assigned_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL, ADD CONSTRAINT `fk_udp_plan` FOREIGN KEY (`plan_id`) REFERENCES `diet_plans` (`plan_id`) ON DELETE CASCADE, ADD CONSTRAINT `fk_udp_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `vaccines` ADD CONSTRAINT `fk_vaccines_category` FOREIGN KEY (`category_id`) REFERENCES `vaccine_categories` (`category_id`) ON UPDATE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;