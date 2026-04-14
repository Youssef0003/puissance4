document.addEventListener('DOMContentLoaded', function() {
    // Gestion des messages flash (disparition automatique)
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 300);
        }, 3000);
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
        },

        updateBoard: function(boardData, container = '.board') {
            const board = document.querySelector(container);
            if (!board) return;

            const cells = board.querySelectorAll('.cell');
            cells.forEach(cell => {
                const row = parseInt(cell.getAttribute('data-row'));
                const col = parseInt(cell.getAttribute('data-col'));
                const value = boardData[row][col];

                cell.className = 'cell';
                if (value === 1) {
                    cell.classList.add('player-1');
                } else if (value === 2) {
                    cell.classList.add('player-2');
                } else {
                    cell.classList.add('empty-cell');
                }
            });
        },

        updateCurrentPlayer: function(player, container = '.player-turn') {
            const playerTurn = document.querySelector(container);
            if (!playerTurn) return;

            const indicator = playerTurn.querySelector('.player-indicator');
            if (indicator) {
                indicator.className = 'player-indicator';
                indicator.classList.add(player === 1 ? 'red' : 'yellow');
            }
        }
    };

    // Animation pour les boutons
    document.querySelectorAll('.btn').forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 6px 12px rgba(0, 0, 0, 0.15)';
        });

        btn.addEventListener('mouseleave', function() {
            this.style.transform = '';
            this.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
        });
    });
});
