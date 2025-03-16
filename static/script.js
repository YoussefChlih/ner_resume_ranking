document.addEventListener('DOMContentLoaded', function() {
    // Auth page tab switching
    const authTabBtns = document.querySelectorAll('.auth-tab-btn');
    const authTabContents = document.querySelectorAll('.auth-tab-content');
    
    if (authTabBtns.length > 0) {
        authTabBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const tabId = this.getAttribute('data-tab');
                
                // Update active tab button
                authTabBtns.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                // Show selected tab content
                authTabContents.forEach(content => {
                    content.classList.remove('active');
                    if (content.id === tabId) {
                        content.classList.add('active');
                    }
                });
            });
        });
        
        // Check URL parameters for pre-selecting user type
        const urlParams = new URLSearchParams(window.location.search);
        const userType = urlParams.get('type');
        
        if (userType) {
            const typeRadios = document.querySelectorAll(`input[name="user_type"][value="${userType}"]`);
            typeRadios.forEach(radio => {
                radio.checked = true;
            });
        }
    }
    
    // Password confirmation validation
    const registerForm = document.querySelector('form[action*="auth"][name="action"][value="register"]');
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            const password = document.getElementById('register-password').value;
            const confirmPassword = document.getElementById('register-confirm').value;
            
            if (password !== confirmPassword) {
                e.preventDefault();
                alert('Passwords do not match!');
            }
        });
    }
    
    // Job search functionality
    const jobSearchInput = document.getElementById('job-search');
    if (jobSearchInput) {
        jobSearchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const jobCards = document.querySelectorAll('.job-card');
            
            jobCards.forEach(card => {
                const title = card.querySelector('h4').textContent.toLowerCase();
                const description = card.querySelector('.job-description-preview').textContent.toLowerCase();
                
                if (title.includes(searchTerm) || description.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }
    
    // Toggle job description
    const toggleButtons = document.querySelectorAll('.toggle-description');
    if (toggleButtons.length > 0) {
        toggleButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const jobCard = this.closest('.job-card');
                const preview = jobCard.querySelector('.job-description-preview');
                const fullDescription = jobCard.querySelector('.full-description');
                
                if (fullDescription.style.display === 'none') {
                    preview.style.display = 'none';
                    fullDescription.style.display = 'block';
                    this.textContent = 'Hide Description';
                } else {
                    preview.style.display = 'block';
                    fullDescription.style.display = 'none';
                    this.textContent = 'View Description';
                }
            });
        });
    }
    
    // Ranking details toggle
    const toggleDetailsButtons = document.querySelectorAll('.toggle-details');
    if (toggleDetailsButtons.length > 0) {
        toggleDetailsButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const card = this.closest('.ranking-card');
                const details = card.querySelector('.full-details');
                
                if (details.style.display === 'none') {
                    details.style.display = 'block';
                    this.textContent = 'Hide Details';
                } else {
                    details.style.display = 'none';
                    this.textContent = 'View Details';
                }
            });
        });
    }
    
    // Add dynamic keyword fields in recruiter page
    const addKeywordBtn = document.getElementById('add-keyword');
    if (addKeywordBtn) {
        addKeywordBtn.addEventListener('click', function() {
            const keywordsContainer = document.querySelector('.keywords-container');
            const newRow = document.createElement('div');
            newRow.className = 'keyword-row';
            
            newRow.innerHTML = `
                <input type="text" name="keyword[]" placeholder="Keyword">
                <input type="number" name="weight[]" placeholder="Weight" min="0" max="1" step="0.1" value="0.5">
                <button type="button" class="btn btn-small remove-keyword">×</button>
            `;
            
            keywordsContainer.appendChild(newRow);
            
            // Add remove functionality to the new button
            const removeBtn = newRow.querySelector('.remove-keyword');
            removeBtn.addEventListener('click', function() {
                keywordsContainer.removeChild(newRow);
            });
        });
    }
    
    // Auto-close flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.message');
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(msg => {
                msg.style.opacity = '0';
                msg.style.transition = 'opacity 0.5s';
                
                setTimeout(() => {
                    msg.remove();
                }, 500);
            });
        }, 5000);
    }
    
    // Apply file input validation
    const resumeInput = document.getElementById('resume');
    if (resumeInput) {
        resumeInput.addEventListener('change', function() {
            const fileName = this.value.toLowerCase();
            if (!fileName.endsWith('.pdf')) {
                alert('Please upload a PDF file only.');
                this.value = '';
            }
            
            // Show file name next to input
            const fileLabel = document.querySelector('label[for="resume"]');
            if (fileLabel && this.files.length > 0) {
                fileLabel.textContent = `Selected: ${this.files[0].name}`;
            }
        });
    }
    
    // Progressive enhancement for rankings visualization
    const rankingCards = document.querySelectorAll('.ranking-card');
    if (rankingCards.length > 0) {
        rankingCards.forEach(card => {
            const percentage = card.querySelector('.match-percentage').textContent;
            const percentValue = parseInt(percentage);
            
            // Add color coding based on match percentage
            if (percentValue >= 80) {
                card.style.borderLeft = '5px solid #27ae60';
            } else if (percentValue >= 60) {
                card.style.borderLeft = '5px solid #f39c12';
            } else {
                card.style.borderLeft = '5px solid #e74c3c';
            }
        });
    }
    const detailsButtons = document.querySelectorAll('.toggle-details');
    if (detailsButtons.length > 0) {
        detailsButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const card = this.closest('.ranking-card');
                const detailsPanel = card.querySelector('.cv-detailed-analysis');
                
                if (detailsPanel.style.display === 'none') {
                    detailsPanel.style.display = 'block';
                    this.textContent = 'Hide Analysis';
                } else {
                    detailsPanel.style.display = 'none';
                    this.textContent = 'View Details';
                }
            });
        });
    }
    
    // Date validation for scheduling interviews
    const interviewDateInput = document.getElementById('interview_date');
    if (interviewDateInput) {
        // Set minimum date to today
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        
        interviewDateInput.min = `${yyyy}-${mm}-${dd}`;
        
        // Add 6 months as max date
        const maxDate = new Date();
        maxDate.setMonth(maxDate.getMonth() + 6);
        const maxYyyy = maxDate.getFullYear();
        const maxMm = String(maxDate.getMonth() + 1).padStart(2, '0');
        const maxDd = String(maxDate.getDate()).padStart(2, '0');
        
        interviewDateInput.max = `${maxYyyy}-${maxMm}-${maxDd}`;
    }
    
    // Message tabs
    const messageTabBtns = document.querySelectorAll('.message-tab-btn');
    const messageTabPanes = document.querySelectorAll('.message-tab-pane');
    
    if (messageTabBtns.length > 0) {
        messageTabBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const tabId = this.getAttribute('data-tab');
                
                // Update active tab button
                messageTabBtns.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                // Show selected tab content
                messageTabPanes.forEach(pane => {
                    pane.classList.remove('active');
                    if (pane.id === tabId) {
                        pane.classList.add('active');
                    }
                });
            });
        });
    }
    
    // Profile picture preview
    const profilePictureInput = document.getElementById('profile_picture');
    if (profilePictureInput) {
        profilePictureInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                const reader = new FileReader();
                
                reader.onload = function(e) {
                    const profilePicture = document.querySelector('.profile-picture img');
                    if (profilePicture) {
                        profilePicture.src = e.target.result;
                    } else {
                        const defaultPicture = document.querySelector('.default-picture');
                        if (defaultPicture) {
                            const newImage = document.createElement('img');
                            newImage.src = e.target.result;
                            newImage.alt = 'Profile Picture';
                            defaultPicture.parentNode.replaceChild(newImage, defaultPicture);
                        }
                    }
                }
                
                reader.readAsDataURL(this.files[0]);
            }
        });
    }
    
    // Enhanced relevance details toggle
    const viewRelevanceButtons = document.querySelectorAll('.view-relevance-btn');
    if (viewRelevanceButtons.length > 0) {
        viewRelevanceButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const card = this.closest('.ranking-card');
                const relevanceDetails = card.querySelector('.relevance-details');
                
                if (relevanceDetails.style.display === 'none') {
                    relevanceDetails.style.display = 'block';
                    this.textContent = 'Hide Relevance Details';
                } else {
                    relevanceDetails.style.display = 'none';
                    this.textContent = 'View Relevance Details';
                }
            });
        });
    }
    
    // Auto close flash messages after 5 seconds
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(msg => {
                msg.style.opacity = '0';
                msg.style.transition = 'opacity 0.5s';
                
                setTimeout(() => {
                    if (msg.parentNode) {
                        msg.parentNode.removeChild(msg);
                    }
                }, 500);
            });
        }, 5000);
    }
});