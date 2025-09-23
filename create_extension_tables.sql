-- Create tables for SMS 21 database


CREATE TABLE instructors (
    id INT IDENTITY(1,1) PRIMARY KEY,
    full_name NVARCHAR(100) NOT NULL,
    email NVARCHAR(255) NOT NULL,
    phone_number NVARCHAR(20) NULL,
    frontcore_id NVARCHAR(50) NULL,
    notes NVARCHAR(MAX) NULL,
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);

CREATE TABLE instructors_coursedates (
    id INT IDENTITY(1,1) PRIMARY KEY,
    instructor_id INT NOT NULL,
    coursedate_id INT NOT NULL,
    new_instructor BIT DEFAULT 0,
    contract_sent BIT DEFAULT 0,
    contract_signed BIT DEFAULT 0,
    info_sent BIT DEFAULT 0,
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE(),
    
    CONSTRAINT FK_instructors_coursedates_instructor 
        FOREIGN KEY (instructor_id) REFERENCES instructors(id),
    CONSTRAINT FK_instructors_coursedates_coursedate 
        FOREIGN KEY (coursedate_id) REFERENCES coursedates(id),
    CONSTRAINT UQ_instructors_coursedates
        UNIQUE (instructor_id, coursedate_id)
);

ALTER TABLE coursedates
ADD responsible NVARCHAR(100),
    billed BIT DEFAULT 0,
    who_billed NVARCHAR(100),
    notes NVARCHAR(MAX);



