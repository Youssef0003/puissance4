document.addEventListener('DOMContentLoaded', function() {
    // Gestion des messages flash (disparition automatique)
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 300);
        }, 3000);
    });

    // Animation pour les boutons
    document.querySelectorAll('.btn, .btn-game').forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 6px 12px rgba(0, 0, 0, 0.15)';
        });

        btn.addEventListener('mouseleave', function() {
            this.style.transform = '';
            this.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
        });
    });

    // Fonction utilitaire pour les requêtes AJAX
    window.gameUtils = {
        sendRequest: function(url, method, data, successCallback, errorCallback) {
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                }
            };

            if (data) {
                options.body = JSON.stringify(data);
            }

            fetch(url, options)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Erreur HTTP: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (successCallback) successCallback(data);
                })
                .catch(error => {
                    console.error('Erreur:', error);
                    if (errorCallback) errorCallback(error);
                    else alert('Une erreur est survenue: ' + error.message);
                });
        }
    };

    // Gestion des modales (si vous en utilisez)
    window.modalUtils = {
        openModal: function(modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.style.display = 'block';
                document.body.style.overflow = 'hidden';
            }
        },

        closeModal: function(modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.style.display = 'none';
                document.body.style.overflow = 'auto';
            }
        }
    };
});
