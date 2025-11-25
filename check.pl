my $prev = -1;

while (<>) {
    chomp;

    my @fields = split(/,/, $_);
    my $cur = int $fields[-2]; 

    printf("$.: bad %d -> %d\n", $prev, $cur) if (
        $prev >= 0 && $cur - $prev != 1
    );
    
    $prev = $cur;
}