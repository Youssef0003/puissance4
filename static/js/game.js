document.addEventListener('DOMContentLoaded', function() {
    // Animation des jetons qui tombent
    function animateTokenDrop(row, col) {
        const cell = document.querySelector(`.cell[data-row="${row}"][data-col="${col}"]`);
        if (cell) {
            cell.classList.add('token-drop');
            setTimeout(() => {
                cell.classList.remove('token-drop');
            }, 500);
        }
    }

    // Mise en évidence du dernier coup
    function highlightLastMove(row, col) {
        const cell = document.querySelector(`.cell[data-row="${row}"][data-col="${col}"]`);
        if (cell) {
            cell.classList.add('last-move');
            setTimeout(() => {
                cell.classList.remove('last-move');
            }, 2000);
        }
    }

    // Mise à jour des scores Minimax avec couleur selon la valeur
    function updateMinimaxScores(scores) {
        const scoreBadges = document.querySelectorAll('.score-badge');
        scoreBadges.forEach((badge, index) => {
            const score = scores[index];
            badge.textContent = score.toFixed(2);

            // Ajouter une classe selon la valeur du score
            badge.className = 'score-badge';
            if (score > 0.7) {
                badge.classList.add('high');
            } else if (score > 0.4) {
                badge.classList.add('medium');
            } else {
                badge.classList.add('low');
            }
        });
    }

    // Gestion des clics sur les colonnes
    const columnHeaders = document.querySelectorAll('.column-header');
    columnHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const col = parseInt(this.getAttribute('data-col'));
            makeMove(col);
        });
    });

    // Fonction pour jouer un coup
    function makeMove(column) {
        fetch('/play', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `column=${column}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
                return;
            }

            // Mise à jour du plateau
            updateBoard(data.board);

            // Animation du dernier coup
            if (data.last_move) {
                animateTokenDrop(data.last_move[0], data.last_move[1]);
                highlightLastMove(data.last_move[0], data.last_move[1]);
            }

            // Mise à jour des scores Minimax si présents
            if (data.minimax_scores) {
                updateMinimaxScores(data.minimax_scores);
            }

            // Gestion de la fin de partie
            if (data.game_over) {
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            alert('Une erreur est survenue');
        });
    }

    // Mise à jour du plateau
    function updateBoard(boardData) {
        const cells = document.querySelectorAll('.cell');
        cells.forEach(cell => {
            const row = parseInt(cell.getAttribute('data-row'));
            const col = parseInt(cell.getAttribute('data-col'));
            const value = boardData[row][col];

            cell.className = 'cell';
            if (value === 1) {  // ROUGE
                cell.classList.add('player-1');
            } else if (value === 2) {  // JAUNE
                cell.classList.add('player-2');
            } else {
                cell.classList.add('empty-cell');
            }

            // Conserver les classes spéciales
            if (cell.classList.contains('winning-cell')) {
                cell.classList.add('winning-cell');
            }
            if (cell.classList.contains('last-move')) {
                cell.classList.add('last-move');
            }
        });
    }

    // Gestion du bouton Annuler
    document.getElementById('undo-btn')?.addEventListener('click', function() {
        fetch('/undo', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
                return;
            }
            window.location.reload();
        })
        .catch(error => {
            console.error('Erreur:', error);
            alert('Une erreur est survenue');
        });
    });

    // Gestion du bouton Recommencer
    document.getElementById('replay-btn')?.addEventListener('click', function() {
        if (confirm('Voulez-vous vraiment recommencer une nouvelle partie?')) {
            window.location.href = '/replay';
        }
    });
});
